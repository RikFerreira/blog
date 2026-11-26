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
import json
import os
import re
import shutil
import sys
import tomllib
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markdown_it import MarkdownIt
from markupsafe import Markup, escape

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
# theme
# ---------------------------------------------------------------------------


# Line weight and grid the handoff draws every icon on.
ICON_STROKE_WIDTH = "1.75"
ICON_VIEWBOX = "0 0 24 24"


def flatten_keys(table: dict, prefix: str = "") -> set[str]:
    """Every leaf of a nested table, as dotted keys."""
    keys: set[str] = set()
    for key, value in table.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            keys |= flatten_keys(value, f"{dotted}.")
        else:
            keys.add(dotted)
    return keys


@dataclass
class Theme:
    """Templates, interface strings and icons for one theme."""

    path: Path
    settings: Settings
    translations: dict[str, dict]
    icons: dict[str, dict]
    env: Environment = field(init=False)

    def __post_init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(self.path / "templates"),
            autoescape=True,
            undefined=StrictUndefined,
            trim_blocks=False,
            lstrip_blocks=False,
        )
        self.env.globals.update(
            settings=self.settings,
            t=self.t,
            ui=self.ui,
            action=self.action,
            icon=self.icon,
            url=self.url,
            lang_tag=self.lang_tag,
            bi=self.bi,
            bi_toml=self.bi_toml,
            labels=self.labels,
            dates=self.dates,
            translated=self.translated,
            slugify=slugify,
            default_lang=self.settings.default_language,
            categories=self.categories,
            meta=self.meta,
            json_for_script=json_for_script,
        )

    # -- interface strings --------------------------------------------------

    def t(self, key: str, language: str | None = None) -> str:
        """One interface string, in `language` or the default one."""
        language = language or self.settings.default_language
        table = self.translations.get(language)
        if table is None:
            raise ContentError(f"{self.path}: no i18n file for language {language!r}")
        value = table
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                raise ContentError(
                    f"{self.path / 'i18n' / (language + '.toml')}: missing string {key!r}"
                )
            value = value[part]
        if isinstance(value, dict):
            raise ContentError(f"{key!r} is a table of strings, not a string")
        return str(value)

    def ui(self, key: str) -> Markup:
        """`data-en` / `data-pt` attributes, which the language switcher swaps."""
        return Markup(
            " ".join(
                f'data-{language}="{escape(self.t(key, language))}"'
                for language in self.settings.languages
            )
        )

    def action(self, key: str) -> Markup:
        """Tooltip and label for an icon button, in every language."""
        default = escape(self.t(key))
        translated = " ".join(
            f'data-{language}-title="{escape(self.t(key, language))}"'
            for language in self.settings.languages
        )
        return Markup(f'title="{default}" aria-label="{default}" {translated}')

    def lang_tag(self, language: str) -> str:
        return self.t("meta.html_lang", language)

    # -- icons --------------------------------------------------------------

    def icon(self, name: str, size: int = 15) -> Markup:
        definition = self.icons.get(name)
        if definition is None:
            raise ContentError(
                f"{self.path / 'icons.toml'}: unknown icon {name!r}; "
                f"defined icons are {', '.join(sorted(self.icons))}"
            )
        linecap = definition.get("linecap")
        linecap_attr = f' stroke-linecap="{linecap}"' if linecap else ""
        return Markup(
            f'<svg width="{size}" height="{size}" viewBox="{ICON_VIEWBOX}" fill="none" '
            f'stroke="currentColor" stroke-width="{ICON_STROKE_WIDTH}"{linecap_attr} '
            f'aria-hidden="true">{definition["body"]}</svg>'
        )

    # -- urls ---------------------------------------------------------------

    def url(self, path: str) -> str:
        base = self.settings.base_url or "/"
        return f"{base.rstrip('/')}/{path.lstrip('/')}"

    # -- rendering ----------------------------------------------------------

    # -- bilingual values ---------------------------------------------------

    def bi(self, values: dict[str, str]) -> Markup:
        """`data-en` / `data-pt` attributes for a value that is not a UI string."""
        return Markup(
            " ".join(
                f'data-{language}="{escape(values.get(language, ""))}"'
                for language in self.settings.languages
            )
        )

    def labels(self, item: "Item", attribute: str) -> dict[str, str]:
        """An item's title or subtitle in every language the site speaks."""
        return {
            language: getattr(item.translation(language), attribute) or ""
            for language in self.settings.languages
        }

    def dates(self, date: dt.date) -> dict[str, str]:
        """A date as `Nov 2026`, in every language."""
        key = MONTH_KEYS[date.month - 1]
        return {
            language: f"{self.t(f'month.{key}', language)} {date.year}"
            for language in self.settings.languages
        }

    def categories(self, item: "Item", section: "Section") -> str:
        """The values `data-category` carries, for the filter bar to match."""
        if section.filter == "language":
            return " ".join(item.languages)
        return " ".join(slugify(tag) for tag in item.tags)

    def meta(self, item: "Item", section: "Section") -> dict[str, str]:
        """The small mono line above an item title, in every language."""
        if section.kind == "publication":
            languages = " / ".join(code.upper() for code in item.languages)
            return {
                language: f"{item.date.year} · {languages}"
                for language in self.settings.languages
            }
        if section.kind == "project":
            tag = item.tags[0] if item.tags else ""
            return {language: tag for language in self.settings.languages}
        return self.dates(item.date)

    def translated(self, value, language: str | None = None) -> str:
        """A TOML value that is either a plain string or a table of languages."""
        language = language or self.settings.default_language
        if isinstance(value, dict):
            return str(value.get(language, value.get(self.settings.default_language, "")))
        return "" if value is None else str(value)

    def bi_toml(self, value) -> Markup:
        """`data-<lang>` attributes for a TOML table of languages."""
        return self.bi({lang: self.translated(value, lang) for lang in self.settings.languages})

    # -- rendering ----------------------------------------------------------

    def context(self, **overrides) -> dict:
        """Page variables, with the defaults every template may read."""
        context = {
            "active_nav": None,
            "page_title": None,
            "page_description": None,
            "map_config": None,
        }
        context.update(overrides)
        return context

    def render(self, template: str, **context) -> str:
        return self.env.get_template(template).render(**self.context(**context))


def load_theme(theme_dir: Path, settings: Settings) -> Theme:
    theme_dir = Path(theme_dir)
    if not (theme_dir / "templates").is_dir():
        raise ContentError(f"{theme_dir}: no templates/ directory")

    translations = {}
    for language in settings.languages:
        path = theme_dir / "i18n" / f"{language}.toml"
        if not path.is_file():
            raise ContentError(f"{theme_dir}: missing i18n file for {language!r} ({path.name})")
        translations[language] = _load_toml(path)

    icons = _load_toml(theme_dir / "icons.toml").get("icons", {})
    return Theme(path=theme_dir, settings=settings, translations=translations, icons=icons)


# ---------------------------------------------------------------------------
# markdown and citations
# ---------------------------------------------------------------------------


MONTH_KEYS = (
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
)

# Raw HTML is enabled: posts embed <video> and <iframe>, and the Markdown is
# written by the site owner, not by visitors.
_MARKDOWN = MarkdownIt("commonmark", {"html": True, "linkify": False}).enable(
    ["table", "strikethrough"]
)

_BIB_FIELD = re.compile(r"(\w+)\s*=\s*\{([^{}]*)\}", re.DOTALL)


def render_markdown(text: str) -> str:
    return _MARKDOWN.render(text)


def slugify(text: str) -> str:
    """`Remote Sensing` becomes `remote-sensing`, for filter keys and anchors."""
    normalised = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in normalised if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")


def format_citation(bibtex: str) -> str:
    """A BibTeX entry as a single readable line, in ABNT shape."""
    fields = {key.lower(): " ".join(value.split()) for key, value in _BIB_FIELD.findall(bibtex)}

    parts = []
    authors = _format_authors(fields.get("author", ""))
    if authors:
        parts.append(authors if authors.endswith(".") else f"{authors}.")
    if title := fields.get("title"):
        parts.append(f"{title}.")

    venue = fields.get("booktitle") or fields.get("journal") or fields.get("publisher")
    year = fields.get("year")
    if venue and year:
        parts.append(f"{venue}, {year}.")
    elif venue:
        parts.append(f"{venue}.")
    elif year:
        parts.append(f"{year}.")

    if doi := fields.get("doi"):
        parts.append(f"https://doi.org/{doi.removeprefix('https://doi.org/')}")

    return " ".join(parts)


def _format_authors(field_value: str) -> str:
    names = [name.strip() for name in field_value.split(" and ") if name.strip()]
    if not names:
        return ""
    formatted = [_format_author(name) for name in names]
    if len(formatted) > 3:
        return f"{formatted[0]} et al."
    return "; ".join(formatted)


def _format_author(name: str) -> str:
    """`Alves, Rik Ferreira` becomes `ALVES, R. F.`."""
    if "," in name:
        family, _, given = name.partition(",")
    else:
        words = name.split()
        family, given = (words[-1], " ".join(words[:-1])) if words else ("", "")
    initials = " ".join(f"{word[0].upper()}." for word in given.split() if word)
    family = family.strip().upper()
    return f"{family}, {initials}" if initials else family


# ---------------------------------------------------------------------------
# areas of interest
# ---------------------------------------------------------------------------


# 0.5 mm at 96 dpi, the base line weight for an AOI outline.
DEFAULT_LINE_WIDTH = 1.9
DEFAULT_LINE_COLOR = "#111111"
DEFAULT_FILL_COLOR = "#111111"
DEFAULT_FILL_OPACITY = 0.06
DEFAULT_ACTIVE_COLOR = "#c83223"
DEFAULT_MAX_VERTICES = 500
DEFAULT_SURFACE = "#f3f2ed"

# The environment variable the style URL interpolates. A static site hands the
# key to every visitor, so restrict it by domain at the provider; keeping it
# out of the repository is housekeeping, not secrecy.
TILES_KEY_VAR = "MAP_TILES_KEY"
TILES_KEY_PLACEHOLDER = "${" + TILES_KEY_VAR + "}"

_WKT_HEAD = re.compile(r"^\s*([A-Za-z]+)\s*(\(.*\))\s*$", re.DOTALL)

AOI_GEOJSON_NAME = "aois.geojson"


def parse_wkt(wkt: str) -> dict:
    """A POLYGON or MULTIPOLYGON in WKT, as a GeoJSON geometry."""
    match = _WKT_HEAD.match(wkt or "")
    if not match:
        raise ContentError(f"aoi_wkt is not well-formed WKT: {wkt!r}")

    keyword, body = match.group(1).upper(), match.group(2)
    if keyword == "POLYGON":
        return {"type": "Polygon", "coordinates": _parse_polygon(body, wkt)}
    if keyword == "MULTIPOLYGON":
        return {
            "type": "MultiPolygon",
            "coordinates": [_parse_polygon(part, wkt) for part in _split_groups(body, wkt)],
        }
    raise ContentError(
        f"aoi_wkt holds a {keyword} geometry; only POLYGON and MULTIPOLYGON are drawn"
    )


def _split_groups(body: str, wkt: str) -> list[str]:
    """Split the top level of a parenthesised WKT body into its groups."""
    inner = body.strip()
    if not (inner.startswith("(") and inner.endswith(")")):
        raise ContentError(f"aoi_wkt is not well-formed WKT: {wkt!r}")
    inner = inner[1:-1]

    groups, depth, start = [], 0, None
    for index, char in enumerate(inner):
        if char == "(":
            if depth == 0:
                start = index
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                groups.append(inner[start : index + 1])
            elif depth < 0:
                raise ContentError(f"aoi_wkt has unbalanced parentheses: {wkt!r}")
    if depth != 0 or not groups:
        raise ContentError(f"aoi_wkt is not well-formed WKT: {wkt!r}")
    return groups


def _parse_polygon(body: str, wkt: str) -> list[list[list[float]]]:
    return [_parse_ring(ring, wkt) for ring in _split_groups(body, wkt)]


def _parse_ring(ring: str, wkt: str) -> list[list[float]]:
    points = []
    for pair in ring.strip().strip("()").split(","):
        numbers = pair.split()
        if len(numbers) < 2:
            raise ContentError(f"aoi_wkt has a coordinate that is not a pair: {pair.strip()!r}")
        try:
            points.append([float(numbers[0]), float(numbers[1])])
        except ValueError:
            raise ContentError(
                f"aoi_wkt has a coordinate that is not a number: {pair.strip()!r}"
            ) from None
    if len(points) < 3:
        raise ContentError(f"aoi_wkt has a ring with fewer than three points: {wkt!r}")
    if points[0] != points[-1]:
        points.append(list(points[0]))
    return points


def thin_ring(ring: list[list[float]], budget: int) -> list[list[float]]:
    """Drop vertices evenly until the ring fits the budget, keeping it closed."""
    if len(ring) <= budget:
        return ring
    # Never below a closed triangle: three distinct points plus the repeat.
    keep = max(3, budget - 1)
    open_ring = ring[:-1]
    step = len(open_ring) / keep
    thinned = [open_ring[int(index * step)] for index in range(keep)]
    thinned.append(list(thinned[0]))
    return thinned


def _thin_geometry(geometry: dict, max_vertices: int) -> dict:
    if geometry["type"] == "Polygon":
        rings = [geometry["coordinates"]]
    else:
        rings = geometry["coordinates"]

    budget = max(1, int(max_vertices))
    thinned = [[thin_ring(ring, budget) for ring in polygon] for polygon in rings]
    if geometry["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": thinned[0]}
    return {"type": "MultiPolygon", "coordinates": thinned}


def aoi_geojson(section: Section, languages: list[str], max_vertices: int) -> dict:
    """The section's areas of interest as a FeatureCollection, with a bbox."""
    features = []
    for item in section.items:
        if not item.aoi_wkt:
            continue
        geometry = _thin_geometry(parse_wkt(item.aoi_wkt), max_vertices)
        properties = {"slug": item.slug, "url": item.url}
        for language in languages:
            properties[f"title_{language}"] = item.title(language)
        features.append(
            {
                "type": "Feature",
                "id": item.slug,
                "geometry": geometry,
                "properties": properties,
            }
        )

    collection = {"type": "FeatureCollection", "features": features}
    bbox = _bbox(features)
    if bbox:
        collection["bbox"] = bbox
    return collection


def _bbox(features: list[dict]) -> list[float] | None:
    points = [point for feature in features for point in _points(feature["geometry"])]
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _points(geometry: dict):
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    for polygon in polygons:
        for ring in polygon:
            yield from ring


def map_config(settings: Settings, environ: dict | None = None) -> dict:
    """Everything aoi-map.js needs, with the tile key resolved."""
    environ = os.environ if environ is None else environ
    table = settings.map
    style = table.get("style")
    key = environ.get(TILES_KEY_VAR, "")

    if not style:
        resolved = _blank_style(table)
    elif TILES_KEY_PLACEHOLDER in style and not key:
        print(
            f"warning: {TILES_KEY_VAR} is not set, so the AOI map falls back to a "
            "plain background instead of vector tiles",
            file=sys.stderr,
        )
        resolved = _blank_style(table)
    else:
        resolved = style.replace(TILES_KEY_PLACEHOLDER, key)

    return {
        "style": resolved,
        "line_color": table.get("line_color", DEFAULT_LINE_COLOR),
        "line_width": table.get("line_width", DEFAULT_LINE_WIDTH),
        "fill_color": table.get("fill_color", DEFAULT_FILL_COLOR),
        "fill_opacity": table.get("fill_opacity", DEFAULT_FILL_OPACITY),
        "active_color": table.get("active_color", DEFAULT_ACTIVE_COLOR),
        "padding": table.get("padding", 24),
        "max_zoom": table.get("max_zoom", 9),
    }


def _blank_style(table: dict) -> dict:
    return {
        "version": 8,
        "sources": {},
        "layers": [
            {
                "id": "background",
                "type": "background",
                "paint": {"background-color": table.get("surface", DEFAULT_SURFACE)},
            }
        ],
    }


def json_for_script(payload) -> Markup:
    """JSON safe to drop inside a <script> element."""
    text = json.dumps(payload, ensure_ascii=False)
    return Markup(text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


# ---------------------------------------------------------------------------
# rendering the site
# ---------------------------------------------------------------------------


def render_site(site: Site, theme: Theme, out_dir: Path) -> list[Path]:
    """Write every page. Returns the paths written, in the order written."""
    out_dir = Path(out_dir)
    written = []

    written.append(_write(out_dir / "index.html", _render_home(site, theme)))

    for section in site.sections.values():
        if section.kind == "cv":
            written.append(
                _write(
                    out_dir / section.name / "index.html",
                    theme.render(
                        "cv.html",
                        section=section,
                        active_nav=section.name,
                        page_title=theme.t(f"nav.{section.name}"),
                    ),
                )
            )
            continue

        if section.kind not in COLLECTION_KINDS:
            continue

        config = None
        if section.map:
            collection = aoi_geojson(
                section,
                theme.settings.languages,
                int(theme.settings.map.get("max_vertices", DEFAULT_MAX_VERTICES)),
            )
            written.append(
                _write(
                    out_dir / section.name / AOI_GEOJSON_NAME,
                    json.dumps(collection, ensure_ascii=False, indent=1),
                )
            )
            config = map_config(theme.settings)
            config["source"] = theme.url(f"{section.url}{AOI_GEOJSON_NAME}")

        written.append(
            _write(
                out_dir / section.name / "index.html",
                theme.render(
                    "list.html",
                    section=section,
                    citations={item.slug: _citation(item) for item in section.items},
                    map_config=config,
                    active_nav=section.name,
                    page_title=theme.t(f"nav.{section.name}"),
                ),
            )
        )
        for item in section.items:
            written.append(
                _write(
                    out_dir / section.name / item.slug / "index.html",
                    theme.render(
                        "item.html",
                        section=section,
                        item=item,
                        bodies=_bodies(item, theme),
                        citation=_citation(item),
                        active_nav=section.name,
                        page_title=theme.labels(item, "title")[theme.settings.default_language],
                    ),
                )
            )

    return written


def _render_home(site: Site, theme: Theme) -> str:
    home = site.settings.home
    sections = site.sections

    def newest(name: str, count: int) -> list[Item]:
        section = sections.get(name)
        return section.items[:count] if section else []

    cv = sections.get("cv")
    current = None
    if cv is not None:
        current = next(
            (entry for entry in cv.data.get("experience", []) if entry.get("current")), None
        )

    return theme.render(
        "home.html",
        active_nav="home",
        sections=sections,
        projects=newest("projects", int(home.get("projects", 2))),
        posts=newest("posts", int(home.get("posts", 1))),
        publications=newest("publications", int(home.get("publications", 1))),
        citations={
            item.slug: _citation(item) for item in newest("publications", int(home.get("publications", 1)))
        },
        current_role=current,
        has_cv=cv is not None,
    )


def _bodies(item: Item, theme: Theme) -> list[dict]:
    """One rendered Markdown block per language the item was written in."""
    blocks = []
    for language in item.languages:
        blocks.append(
            {
                "language": language,
                "html": Markup(render_markdown(item.translations[language].body)),
                "is_default": language == item.primary_language,
            }
        )
    return blocks


def _citation(item: Item) -> str | None:
    if not item.citation:
        return None
    return format_citation((item.source_dir / item.citation).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# assets
# ---------------------------------------------------------------------------


def copy_assets(site: Site, theme: Theme, out_dir: Path) -> list[Path]:
    """Copy the theme's static files and everything content/ ships with.

    Covers are cropped by CSS rather than resized here, so no image is
    processed: this is a copy, skipping files the output already has.
    """
    out_dir = Path(out_dir)
    copied: list[Path] = []

    copied += _copy_tree(theme.path / "static", out_dir)
    copied += _copy_tree(site.content_dir / "assets", out_dir / "assets")

    for section in site.collections():
        for item in section.items:
            copied += _copy_tree(
                item.source_dir,
                out_dir / section.name / item.slug,
                skip=_is_markdown_source,
            )

    return copied


def _is_markdown_source(path: Path) -> bool:
    return path.name.startswith(CONTENT_FILE_PREFIX) and path.suffix == CONTENT_FILE_SUFFIX


def _copy_tree(source: Path, target: Path, skip=None) -> list[Path]:
    if not source.is_dir():
        return []

    copied = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or (skip and skip(path)):
            continue
        destination = target / path.relative_to(source)
        if _is_current(path, destination):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        copied.append(destination)
    return copied


def _is_current(source: Path, destination: Path) -> bool:
    if not destination.exists():
        return False
    existing = destination.stat()
    original = source.stat()
    return existing.st_mtime_ns >= original.st_mtime_ns and existing.st_size == original.st_size


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--content", type=Path, default=here / "content")
    parser.add_argument("--themes", type=Path, default=here / "themes")
    parser.add_argument("--out", type=Path, default=here / "site")
    args = parser.parse_args(argv)

    try:
        site = load_site(args.content)
        theme = load_theme(args.themes / site.settings.theme, site.settings)
        written = render_site(site, theme, args.out)
        copied = copy_assets(site, theme, args.out)
    except ContentError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"{len(written)} page(s) and {len(copied)} asset(s) written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
