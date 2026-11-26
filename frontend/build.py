#!/usr/bin/env python3
"""Static site generator for rikalves.com.

Reads `content/` — Markdown with YAML front matter, TOML settings and assets —
and writes a static site to `site/`.

Content is organised in three levels:

    index.toml                      level 1: the homepage and global settings
    <section>/<section>.toml        level 2: one section index page
    <section>/<slug>/content.<lang>.md
                                    level 3: one item, one file per language

An item keeps every language it was written in and renders to a single URL;
the language selector swaps the body along with the interface.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

# Front matter keys an item may declare. Anything else fails the build rather
# than being silently dropped.
ITEM_KEYS = frozenset(
    {
        "title",
        "subtitle",
        "date",
        "cover",
        "tags",
        "language",
        "ai_written",
        "external_link",
        "source_repo",
        "aoi_wkt",
        "citation",
    }
)

# Keys that belong to one language. Everything else describes the item itself
# and is read from its primary-language file.
TRANSLATABLE_KEYS = frozenset({"title", "subtitle"})

# Sections that hold items rather than being a single page.
COLLECTION_KINDS = frozenset({"post", "publication", "project"})

CONTENT_FILE_SUFFIX = ".md"
CONTENT_FILE_PREFIX = "content."

# Directories under `content/` that are not sections.
RESERVED_DIRS = frozenset({"assets"})


class ContentError(Exception):
    """Content or settings the generator refuses to render."""


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Translation:
    """One item as written in one language."""

    language: str
    title: str
    subtitle: str | None
    body: str
    source: Path
    is_fallback: bool = False


@dataclass
class Item:
    """A level-3 content directory."""

    section: str
    slug: str
    source_dir: Path
    primary_language: str
    translations: dict[str, Translation]
    date: dt.date
    tags: list[str] = field(default_factory=list)
    cover: str | None = None
    citation: str | None = None
    aoi_wkt: str | None = None
    external_link: str | None = None
    source_repo: str | None = None
    ai_written: bool = False

    @property
    def languages(self) -> list[str]:
        return sorted(self.translations)

    @property
    def url(self) -> str:
        return f"/{self.section}/{self.slug}/"

    def translation(self, language: str) -> Translation:
        """The item in `language`, or its primary language flagged as a fallback."""
        found = self.translations.get(language)
        if found is not None:
            return found
        return replace(self.translations[self.primary_language], is_fallback=True)

    def title(self, language: str) -> str:
        return self.translation(language).title


@dataclass
class Section:
    """A level-2 directory: a collection of items, or a standalone page."""

    name: str
    kind: str
    source_dir: Path
    data: dict
    items: list[Item] = field(default_factory=list)
    sort: str = "date"
    order: str = "desc"
    filter: str | None = None
    map: bool = False

    @property
    def url(self) -> str:
        return f"/{self.name}/"

    @property
    def tags(self) -> list[str]:
        """Every tag used in the section, for the filter bar."""
        return sorted({tag for item in self.items for tag in item.tags})

    @property
    def item_languages(self) -> list[str]:
        return sorted({lang for item in self.items for lang in item.languages})


@dataclass
class Settings:
    """`index.toml` — the homepage and everything global."""

    data: dict
    source: Path

    @property
    def site(self) -> dict:
        return self.data.get("site", {})

    @property
    def title(self) -> str:
        return self.site.get("title", "")

    @property
    def base_url(self) -> str:
        return self.site.get("base_url", "/")

    @property
    def theme(self) -> str:
        return self.site.get("theme", "blog-plain")

    @property
    def default_language(self) -> str:
        return self.site.get("default_language", "en")

    @property
    def languages(self) -> list[str]:
        return list(self.site.get("languages", [self.default_language]))

    @property
    def profile(self) -> dict:
        return self.data.get("profile", {})

    @property
    def nav(self) -> list[dict]:
        return list(self.data.get("nav", []))

    @property
    def links(self) -> list[dict]:
        return list(self.data.get("links", []))

    @property
    def map(self) -> dict:
        return self.data.get("map", {})

    @property
    def home(self) -> dict:
        return self.data.get("home", {})


@dataclass
class Site:
    """Everything the templates need, with no file system left to touch."""

    settings: Settings
    sections: dict[str, Section]
    content_dir: Path

    def collections(self) -> list[Section]:
        return [s for s in self.sections.values() if s.kind in COLLECTION_KINDS]

    def items(self) -> list[Item]:
        return [item for section in self.collections() for item in section.items]


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def parse_front_matter(text: str, source: Path | None = None) -> tuple[dict, str]:
    """Split a `---` delimited YAML block from the Markdown body after it."""
    where = f" in {source}" if source else ""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ContentError(f"missing YAML front matter{where}: the file must open with ---")

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            block = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            break
    else:
        raise ContentError(f"unterminated YAML front matter{where}: no closing ---")

    try:
        meta = yaml.safe_load(block) or {}
    except yaml.YAMLError as error:
        raise ContentError(f"invalid YAML front matter{where}: {error}") from error
    if not isinstance(meta, dict):
        raise ContentError(f"invalid YAML front matter{where}: expected a mapping")
    return meta, body


def _load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        raise ContentError(f"missing {path}") from None
    except tomllib.TOMLDecodeError as error:
        raise ContentError(f"invalid TOML in {path}: {error}") from error


def _coerce_date(value, where: str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ContentError(f"invalid date in {where}: expected YYYY-MM-DD, got {value!r}")


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def load_site(content_dir: Path) -> Site:
    """Read the whole content tree, or raise ContentError naming the file at fault."""
    content_dir = Path(content_dir)
    index = content_dir / "index.toml"
    if not index.is_file():
        raise ContentError(f"missing index.toml in {content_dir}")

    settings = Settings(data=_load_toml(index), source=index)
    _validate_settings(settings)

    sections: dict[str, Section] = {}
    for directory in sorted(p for p in content_dir.iterdir() if p.is_dir()):
        if directory.name.startswith(".") or directory.name in RESERVED_DIRS:
            continue
        section = _load_section(directory, settings, content_dir)
        sections[section.name] = section

    return Site(settings=settings, sections=sections, content_dir=content_dir)


def _validate_settings(settings: Settings) -> None:
    languages = settings.languages
    if not languages:
        raise ContentError(f"{settings.source}: [site].languages must list at least one language")
    if settings.default_language not in languages:
        raise ContentError(
            f"{settings.source}: [site].default_language {settings.default_language!r} "
            f"is not in [site].languages {languages}"
        )


def _load_section(directory: Path, settings: Settings, content_dir: Path) -> Section:
    name = directory.name
    toml_path = directory / f"{name}.toml"
    if not toml_path.is_file():
        raise ContentError(
            f"{_relative(directory, content_dir)}: a section directory needs {name}.toml"
        )

    data = _load_toml(toml_path)
    table = data.get("section", {})
    section = Section(
        name=name,
        kind=table.get("kind", "post"),
        source_dir=directory,
        data={key: value for key, value in data.items() if key != "section"},
        sort=table.get("sort", "date"),
        order=table.get("order", "desc"),
        filter=table.get("filter"),
        map=bool(table.get("map", False)),
    )

    if section.kind in COLLECTION_KINDS:
        for item_dir in sorted(p for p in directory.iterdir() if p.is_dir()):
            if item_dir.name.startswith("."):
                continue
            section.items.append(_load_item(item_dir, name, settings, content_dir))
        _sort_items(section)

    return section


def _sort_items(section: Section) -> None:
    if section.sort == "title":
        key = lambda item: item.title(item.primary_language).casefold()  # noqa: E731
    elif section.sort == "date":
        key = lambda item: item.date  # noqa: E731
    else:
        raise ContentError(
            f"{section.source_dir}: unknown [section].sort {section.sort!r} "
            "(expected 'date' or 'title')"
        )
    section.items.sort(key=key, reverse=section.order == "desc")


def _load_item(item_dir: Path, section_name: str, settings: Settings, content_dir: Path) -> Item:
    sources = _language_files(item_dir, content_dir)
    metas: dict[str, dict] = {}
    translations: dict[str, Translation] = {}

    for language, path in sources.items():
        where = _relative(path, content_dir)
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path)
        _validate_item_keys(meta, where)

        if language not in settings.languages:
            raise ContentError(
                f"{where}: language {language!r} is not in [site].languages "
                f"{settings.languages}"
            )
        declared = meta.get("language")
        if declared is None:
            raise ContentError(f"{where}: missing 'language'")
        if declared != language:
            raise ContentError(
                f"{where}: 'language' is {declared!r} but the file name says {language!r}"
            )
        title = meta.get("title")
        if not title:
            raise ContentError(f"{where}: missing 'title'")

        metas[language] = meta
        translations[language] = Translation(
            language=language,
            title=str(title),
            subtitle=_optional_str(meta, "subtitle", where),
            body=body,
            source=path,
        )

    primary = (
        settings.default_language
        if settings.default_language in translations
        else next(lang for lang in settings.languages if lang in translations)
    )
    meta = metas[primary]
    where = _relative(sources[primary], content_dir)

    if "date" not in meta:
        raise ContentError(f"{where}: missing 'date'")

    return Item(
        section=section_name,
        slug=item_dir.name,
        source_dir=item_dir,
        primary_language=primary,
        translations=translations,
        date=_coerce_date(meta["date"], where),
        tags=_tag_list(meta, where),
        cover=_relative_file(meta, "cover", item_dir, where),
        citation=_relative_file(meta, "citation", item_dir, where),
        aoi_wkt=_optional_str(meta, "aoi_wkt", where),
        external_link=_optional_str(meta, "external_link", where),
        source_repo=_optional_str(meta, "source_repo", where),
        ai_written=_flag(meta, "ai_written", where),
    )


def _language_files(item_dir: Path, content_dir: Path) -> dict[str, Path]:
    """Map language code to `content.<lang>.md`, in file name order."""
    found: dict[str, Path] = {}
    for path in sorted(item_dir.glob(f"{CONTENT_FILE_PREFIX}*{CONTENT_FILE_SUFFIX}")):
        language = path.name[len(CONTENT_FILE_PREFIX) : -len(CONTENT_FILE_SUFFIX)]
        if language:
            found[language] = path
    if not found:
        raise ContentError(
            f"{_relative(item_dir, content_dir)}: no content.<lang>.md in this item directory"
        )
    return found


def _validate_item_keys(meta: dict, where: str) -> None:
    unknown = sorted(set(meta) - ITEM_KEYS)
    if unknown:
        raise ContentError(
            f"{where}: unknown front matter key(s) {', '.join(unknown)}; "
            f"allowed keys are {', '.join(sorted(ITEM_KEYS))}"
        )


def _optional_str(meta: dict, key: str, where: str) -> str | None:
    value = meta.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContentError(f"{where}: '{key}' must be a string, got {type(value).__name__}")
    return value


def _tag_list(meta: dict, where: str) -> list[str]:
    value = meta.get("tags")
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(tag, str) for tag in value):
        raise ContentError(f"{where}: 'tags' must be a list of strings, got {value!r}")
    return list(value)


def _flag(meta: dict, key: str, where: str) -> bool:
    value = meta.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ContentError(f"{where}: '{key}' must be true or false, got {value!r}")
    return value


def _relative_file(meta: dict, key: str, item_dir: Path, where: str) -> str | None:
    value = _optional_str(meta, key, where)
    if value is None:
        return None
    if not (item_dir / value).is_file():
        raise ContentError(f"{where}: '{key}' points at {value}, which does not exist")
    return value


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--content", type=Path, default=here / "content")
    args = parser.parse_args(argv)

    try:
        site = load_site(args.content)
    except ContentError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    for section in site.sections.values():
        print(f"{section.name}: {section.kind}, {len(section.items)} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
