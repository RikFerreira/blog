"""The content model: TOML settings, bilingual front matter, item ordering."""

import datetime as dt

import pytest

from build import ContentError, load_site, parse_front_matter


# --------------------------------------------------------------------------
# front matter
# --------------------------------------------------------------------------

def test_parse_front_matter_splits_metadata_from_body():
    meta, body = parse_front_matter("---\ntitle: Hi\n---\n\nFirst line.\n")
    assert meta == {"title": "Hi"}
    assert body.strip() == "First line."


def test_parse_front_matter_rejects_a_file_without_a_block():
    with pytest.raises(ContentError, match="front matter"):
        parse_front_matter("No block here.\n")


def test_parse_front_matter_rejects_an_unterminated_block():
    with pytest.raises(ContentError, match="front matter"):
        parse_front_matter("---\ntitle: Hi\n\nbody\n")


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------

def test_settings_come_from_index_toml(fixture_content):
    site = load_site(fixture_content)
    assert site.settings.title == "rikalves.com"
    assert site.settings.default_language == "en"
    assert site.settings.languages == ["en", "pt"]
    assert site.settings.theme == "blog-plain"
    assert site.settings.map["max_vertices"] == 50
    assert site.settings.profile["name"] == "Rik Ferreira Alves"
    assert [entry["key"] for entry in site.settings.nav] == [
        "home",
        "projects",
        "posts",
        "publications",
        "cv",
    ]


def test_default_language_must_be_one_of_the_declared_languages(make_content):
    root = make_content(
        {
            "index.toml": (
                '[site]\n'
                'title            = "test"\n'
                'default_language = "de"\n'
                'languages        = ["en", "pt"]\n'
            )
        },
        with_defaults=False,
    )
    with pytest.raises(ContentError, match="default_language"):
        load_site(root)


def test_a_missing_index_toml_is_an_error(tmp_path):
    (tmp_path / "content").mkdir()
    with pytest.raises(ContentError, match="index.toml"):
        load_site(tmp_path / "content")


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------

def test_sections_are_discovered_with_their_settings(fixture_content):
    site = load_site(fixture_content)
    assert set(site.sections) == {"posts", "publications", "projects", "cv"}
    assert site.sections["publications"].kind == "publication"
    assert site.sections["publications"].filter == "language"
    assert site.sections["publications"].map is True
    assert site.sections["posts"].filter == "tags"
    assert site.sections["projects"].sort == "title"


def test_the_cv_section_is_a_page_and_keeps_its_raw_table(fixture_content):
    cv = load_site(fixture_content).sections["cv"]
    assert cv.kind == "cv"
    assert cv.items == []
    assert cv.data["experience"][0]["role"]["en"] == "GIS Analyst - TPF Engenharia"


def test_a_section_directory_without_its_toml_is_an_error(make_content):
    root = make_content(
        {"orphan/thing/content.en.md": "---\ntitle: X\nlanguage: en\n---\n"}
    )
    with pytest.raises(ContentError, match="orphan"):
        load_site(root)


# --------------------------------------------------------------------------
# items and translations
# --------------------------------------------------------------------------

def test_an_item_carries_every_language_it_was_written_in(fixture_content):
    item = _item(load_site(fixture_content), "posts", "hello-world")
    assert item.languages == ["en", "pt"]
    assert item.url == "/posts/hello-world/"
    assert item.translation("en").title.startswith("Combining Sentinel-2")
    assert item.translation("pt").title.startswith("Combinando Sentinel-2")
    assert item.translation("pt").is_fallback is False
    assert "relevo importa" in item.translation("pt").body


def test_invariant_fields_come_from_the_default_language_file(fixture_content):
    item = _item(load_site(fixture_content), "posts", "hello-world")
    assert item.date == dt.date(2026, 11, 4)
    assert item.tags == ["Remote Sensing", "Sentinel-2"]
    assert item.cover == "assets/cover.png"
    assert item.ai_written is False


def test_a_missing_translation_falls_back_and_says_so(fixture_content):
    item = _item(load_site(fixture_content), "posts", "so-portugues")
    assert item.languages == ["pt"]
    english = item.translation("en")
    assert english.language == "pt"
    assert english.is_fallback is True


def test_publication_fields_are_read(fixture_content):
    item = _item(load_site(fixture_content), "publications", "veredas")
    assert item.citation == "cite.bib"
    assert item.external_link == "https://example.org/paper"
    assert item.aoi_wkt.startswith("POLYGON")


def test_items_are_sorted_newest_first(make_content):
    root = make_content(
        {
            "posts/old/content.en.md": _post("Old", "2024-01-01"),
            "posts/new/content.en.md": _post("New", "2026-01-01"),
            "posts/middle/content.en.md": _post("Middle", "2025-01-01"),
        }
    )
    slugs = [item.slug for item in load_site(root).sections["posts"].items]
    assert slugs == ["new", "middle", "old"]


def test_a_section_can_sort_by_title_ascending(make_content):
    root = make_content(
        {
            "posts/posts.toml": (
                '[section]\nkind = "post"\nsort = "title"\norder = "asc"\n'
            ),
            "posts/b/content.en.md": _post("Beta", "2026-01-01"),
            "posts/a/content.en.md": _post("Alpha", "2024-01-01"),
        }
    )
    slugs = [item.slug for item in load_site(root).sections["posts"].items]
    assert slugs == ["a", "b"]


def test_every_tag_used_in_a_section_is_collected_for_the_filter_bar(fixture_content):
    posts = load_site(fixture_content).sections["posts"]
    assert posts.tags == ["GIS", "Remote Sensing", "Sentinel-2"]


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def test_an_unknown_front_matter_key_is_an_error(make_content):
    root = make_content(
        {
            "posts/x/content.en.md": (
                "---\ntitle: X\nlanguage: en\ndate: 2026-01-01\nweight: 3\n---\n"
            )
        }
    )
    with pytest.raises(ContentError, match="weight"):
        load_site(root)


def test_a_missing_title_is_an_error(make_content):
    root = make_content(
        {"posts/x/content.en.md": "---\nlanguage: en\ndate: 2026-01-01\n---\n"}
    )
    with pytest.raises(ContentError, match="title"):
        load_site(root)


def test_the_language_key_must_match_the_file_name(make_content):
    root = make_content(
        {"posts/x/content.en.md": _post("X", "2026-01-01", language="pt")}
    )
    with pytest.raises(ContentError, match="language"):
        load_site(root)


def test_a_language_outside_the_declared_set_is_an_error(make_content):
    root = make_content(
        {"posts/x/content.fr.md": _post("X", "2026-01-01", language="fr")}
    )
    with pytest.raises(ContentError, match="fr"):
        load_site(root)


def test_the_default_language_file_must_carry_the_date(make_content):
    root = make_content({"posts/x/content.en.md": "---\ntitle: X\nlanguage: en\n---\n"})
    with pytest.raises(ContentError, match="date"):
        load_site(root)


def test_an_unparseable_date_is_an_error(make_content):
    root = make_content({"posts/x/content.en.md": _post("X", "04/11/2026")})
    with pytest.raises(ContentError, match="date"):
        load_site(root)


def test_a_cover_that_does_not_exist_is_an_error(make_content):
    root = make_content(
        {
            "posts/x/content.en.md": _post(
                "X", "2026-01-01", extra="cover: assets/nope.png\n"
            )
        }
    )
    with pytest.raises(ContentError, match="cover"):
        load_site(root)


def test_a_citation_that_does_not_exist_is_an_error(make_content):
    root = make_content(
        {"posts/x/content.en.md": _post("X", "2026-01-01", extra="citation: cite.bib\n")}
    )
    with pytest.raises(ContentError, match="cite.bib"):
        load_site(root)


def test_tags_must_be_a_list(make_content):
    root = make_content(
        {"posts/x/content.en.md": _post("X", "2026-01-01", extra="tags: GIS\n")}
    )
    with pytest.raises(ContentError, match="tags"):
        load_site(root)


def test_ai_written_must_be_a_boolean(make_content):
    root = make_content(
        {"posts/x/content.en.md": _post("X", "2026-01-01", extra="ai_written: yep\n")}
    )
    with pytest.raises(ContentError, match="ai_written"):
        load_site(root)


def test_an_item_directory_with_no_markdown_is_an_error(make_content):
    root = make_content({"posts/x/assets/stray.png": ""})
    with pytest.raises(ContentError, match="posts.x"):
        load_site(root)


def test_the_error_message_names_the_offending_file(make_content):
    root = make_content({"posts/x/content.en.md": "---\nlanguage: en\n---\n"})
    with pytest.raises(ContentError, match=r"posts[/\\]x[/\\]content\.en\.md"):
        load_site(root)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _post(title, date, *, language="en", extra=""):
    return (
        f"---\ntitle: {title}\ndate: {date}\nlanguage: {language}\n{extra}"
        "---\n\nBody.\n"
    )


def _item(site, section, slug):
    return next(i for i in site.sections[section].items if i.slug == slug)
