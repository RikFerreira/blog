"""The rendered pages: home, section indexes, item pages and the CV."""

import pytest

from build import format_citation, load_site, load_theme, render_markdown, render_site


@pytest.fixture
def rendered(fixture_content, theme_dir, tmp_path):
    site = load_site(fixture_content)
    theme = load_theme(theme_dir, site.settings)
    render_site(site, theme, tmp_path / "site")
    return tmp_path / "site"


def read(root, *parts):
    return (root.joinpath(*parts)).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------

def test_markdown_becomes_html():
    assert "<h2>Why</h2>" in render_markdown("## Why\n")
    assert "<em>veredas</em>" in render_markdown("*veredas*\n")


def test_raw_html_survives_because_posts_embed_video():
    source = '<video controls src="assets/clip.mp4"></video>\n'
    assert "<video" in render_markdown(source)


def test_tables_are_supported():
    table = "| a | b |\n| - | - |\n| 1 | 2 |\n"
    assert "<table>" in render_markdown(table)


# --------------------------------------------------------------------------
# citations
# --------------------------------------------------------------------------

def test_a_bibtex_entry_becomes_a_readable_citation():
    bib = """
@inproceedings{key,
  author    = {Alves, Rik Ferreira and Silva, Claudionor Ribeiro da},
  title     = {Mapping Veredas in the Cerrado},
  booktitle = {XIV Brazilian Colloquium},
  year      = {2026}
}
"""
    assert format_citation(bib) == (
        "ALVES, R. F.; SILVA, C. R. D. Mapping Veredas in the Cerrado. "
        "XIV Brazilian Colloquium, 2026."
    )


def test_more_than_three_authors_collapse_to_et_al():
    bib = (
        "@article{k,\n author = {A, One and B, Two and C, Three and D, Four},\n"
        " title = {T},\n journal = {J},\n year = {2020}\n}\n"
    )
    assert "A, O. et al." in format_citation(bib)


def test_a_doi_is_appended_when_present():
    bib = (
        "@article{k,\n author = {A, One},\n title = {T},\n journal = {J},\n"
        " year = {2020},\n doi = {10.1000/xyz}\n}\n"
    )
    assert format_citation(bib).endswith("https://doi.org/10.1000/xyz")


# --------------------------------------------------------------------------
# what gets written
# --------------------------------------------------------------------------

def test_every_page_is_written_to_its_url(rendered):
    for relative in (
        "index.html",
        "posts/index.html",
        "posts/hello-world/index.html",
        "posts/so-portugues/index.html",
        "publications/index.html",
        "publications/veredas/index.html",
        "projects/index.html",
        "projects/veredas-monitor/index.html",
        "cv/index.html",
    ):
        assert (rendered / relative).is_file(), f"missing {relative}"


# --------------------------------------------------------------------------
# home
# --------------------------------------------------------------------------

def test_the_home_page_leads_with_the_profile(rendered):
    html = read(rendered, "index.html")
    assert "<h1>Rik Ferreira Alves</h1>" in html
    assert 'data-pt="Geografo focado' in html


def test_the_home_page_shows_the_newest_item_of_each_kind(rendered):
    html = read(rendered, "index.html")
    assert "Combining Sentinel-2" in html
    assert "Mapping Veredas in the Cerrado" in html
    assert "Veredas Monitor" in html
    # so-portugues is older than hello-world and [home].posts is 1.
    assert "Convencoes de esquema" not in html


def test_the_home_page_links_on_to_each_section(rendered):
    html = read(rendered, "index.html")
    for href in ('href="/posts/"', 'href="/publications/"', 'href="/projects/"', 'href="/cv/"'):
        assert href in html


# --------------------------------------------------------------------------
# section indexes
# --------------------------------------------------------------------------

def test_a_section_index_lists_every_item(rendered):
    html = read(rendered, "posts/index.html")
    assert html.count("data-list-item") == 2
    assert 'href="/posts/hello-world/"' in html


def test_a_tag_filtered_section_offers_one_button_per_tag(rendered):
    html = read(rendered, "posts/index.html")
    assert 'data-filter="all"' in html
    assert 'data-filter="gis"' in html
    assert 'data-filter="remote-sensing"' in html
    assert 'data-filter="sentinel-2"' in html


def test_an_item_carries_every_tag_it_has_so_the_filter_can_match(rendered):
    html = read(rendered, "posts/index.html")
    assert 'data-category="remote-sensing sentinel-2"' in html


def test_a_language_filtered_section_offers_the_languages_in_use(rendered):
    html = read(rendered, "publications/index.html")
    assert 'data-filter="en"' in html
    assert 'data-filter="remote-sensing"' not in html


def test_publications_carry_a_citation_block_with_a_copy_button(rendered):
    html = read(rendered, "publications/index.html")
    assert "ALVES, R. F." in html
    assert 'data-cite-target="cite-veredas"' in html
    assert 'data-copy-target="cite-veredas-text"' in html


def test_a_project_links_to_its_source_and_to_the_running_app(rendered):
    html = read(rendered, "projects/index.html")
    assert 'href="https://github.com/RikFerreira/veredas-monitor"' in html
    assert 'href="https://veredas.example.org/"' in html


# --------------------------------------------------------------------------
# item pages
# --------------------------------------------------------------------------

def test_an_item_page_carries_one_body_per_language(rendered):
    html = read(rendered, "posts/hello-world/index.html")
    assert 'data-lang-body="en"' in html
    assert 'data-lang-body="pt"' in html
    assert "Why terrain matters" in html
    assert "Por que o relevo importa" in html


def test_the_default_language_body_is_the_one_shown_first(rendered):
    html = read(rendered, "posts/hello-world/index.html")
    assert 'data-lang-body="en" data-lang-default' in html
    assert 'data-lang-body="pt" class="hidden"' in html


def test_the_title_of_an_item_page_is_bilingual(rendered):
    html = read(rendered, "posts/hello-world/index.html")
    assert 'data-pt="Combinando Sentinel-2' in html


def test_an_item_written_in_one_language_says_so(rendered):
    html = read(rendered, "posts/so-portugues/index.html")
    assert 'data-lang-body="pt" data-lang-default' in html
    assert "data-lang-body=\"en\"" not in html
    assert "original_language" not in html
    assert "idioma em que foi escrito" in html


def test_an_item_page_shows_its_cover_when_it_has_one(rendered):
    html = read(rendered, "posts/hello-world/index.html")
    assert 'src="/posts/hello-world/assets/cover.png"' in html


def test_an_item_page_offers_a_way_back_to_its_section(rendered):
    html = read(rendered, "posts/hello-world/index.html")
    assert 'href="/posts/"' in html


def test_the_date_is_written_in_both_languages(rendered):
    html = read(rendered, "posts/hello-world/index.html")
    assert 'data-en="Nov 2026" data-pt="Nov 2026"' in html
    html = read(rendered, "posts/so-portugues/index.html")
    assert 'data-en="Oct 2026" data-pt="Out 2026"' in html


# --------------------------------------------------------------------------
# cv
# --------------------------------------------------------------------------

def test_the_cv_page_renders_each_block(rendered):
    html = read(rendered, "cv/index.html")
    assert "GIS Analyst - TPF Engenharia" in html
    assert "M.Sc. in Geography - UFU" in html
    assert "XIV Brazilian Colloquium on Geodetic Sciences" in html
    assert "Geographic Database Administration" in html


def test_the_current_role_is_marked(rendered):
    html = read(rendered, "cv/index.html")
    assert "cv-current" in html


def test_the_cv_offers_printing_and_keeps_the_chrome_off_the_page(rendered):
    html = read(rendered, "cv/index.html")
    assert "window.print()" in html
    assert "no-print" in html
