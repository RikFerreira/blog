"""The `doi` front matter key: validation, the link, and the citation tail."""

import pytest

from build import ContentError, doi_url, format_citation, load_site, load_theme, render_site


def _publication(doi, *, citation=""):
    return (
        "---\ntitle: A paper\ndate: 2026-01-01\nlanguage: en\n"
        f"doi: {doi}\n{citation}---\n\nBody.\n"
    )


SECTION = '[section]\nkind = "publication"\n'


# --------------------------------------------------------------------------
# normalising what people paste
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "written",
    [
        "10.5281/zenodo.22885603",
        "https://doi.org/10.5281/zenodo.22885603",
        "http://doi.org/10.5281/zenodo.22885603",
        "https://dx.doi.org/10.5281/zenodo.22885603",
        "doi:10.5281/zenodo.22885603",
        "  10.5281/zenodo.22885603  ",
    ],
)
def test_every_way_of_writing_a_doi_resolves_to_one_url(written):
    assert doi_url(written) == "https://doi.org/10.5281/zenodo.22885603"


@pytest.mark.parametrize(
    "written",
    ["not-a-doi", "11.5281/zenodo.1", "10.5281", "https://example.org/paper", "10./x"],
)
def test_something_that_is_not_a_doi_is_refused(written):
    with pytest.raises(ContentError, match="doi"):
        doi_url(written)


# --------------------------------------------------------------------------
# the content model
# --------------------------------------------------------------------------

def test_an_item_keeps_the_doi_as_written_and_offers_the_url(make_content):
    root = make_content(
        {
            "publications/publications.toml": SECTION,
            "publications/p/content.en.md": _publication("10.5281/zenodo.22885603"),
        }
    )
    item = load_site(root).sections["publications"].items[0]
    assert item.doi == "10.5281/zenodo.22885603"
    assert item.doi_url == "https://doi.org/10.5281/zenodo.22885603"


def test_an_item_without_a_doi_has_none(make_content):
    root = make_content(
        {
            "publications/publications.toml": SECTION,
            "publications/p/content.en.md": (
                "---\ntitle: A paper\ndate: 2026-01-01\nlanguage: en\n---\n"
            ),
        }
    )
    item = load_site(root).sections["publications"].items[0]
    assert item.doi is None
    assert item.doi_url is None


def test_a_malformed_doi_fails_the_build_naming_the_file(make_content):
    root = make_content(
        {
            "publications/publications.toml": SECTION,
            "publications/p/content.en.md": _publication("nonsense"),
        }
    )
    with pytest.raises(ContentError, match=r"publications[/\\]p[/\\]content\.en\.md"):
        load_site(root)


# --------------------------------------------------------------------------
# citations
# --------------------------------------------------------------------------

def test_the_front_matter_doi_closes_a_citation_that_has_none():
    bib = (
        "@inproceedings{k,\n author = {A, One},\n title = {T},\n"
        " booktitle = {Conf},\n year = 2026,\n}\n"
    )
    assert format_citation(bib, doi="10.5281/zenodo.22885603").endswith(
        "https://doi.org/10.5281/zenodo.22885603"
    )


def test_the_front_matter_wins_over_a_stale_doi_in_the_bib():
    """The .bib is often imported once; the front matter is maintained here."""
    bib = (
        "@article{k,\n author = {A, One},\n title = {T},\n year = {2020},\n"
        " doi = {10.1000/old}\n}\n"
    )
    citation = format_citation(bib, doi="10.5281/zenodo.22885603")
    assert citation.endswith("https://doi.org/10.5281/zenodo.22885603")
    assert "10.1000/old" not in citation


def test_the_bib_doi_still_stands_on_its_own():
    bib = "@article{k,\n author = {A, One},\n title = {T},\n doi = {10.1000/x}\n}\n"
    assert format_citation(bib).endswith("https://doi.org/10.1000/x")


# --------------------------------------------------------------------------
# the rendered page
# --------------------------------------------------------------------------

@pytest.fixture
def render(make_content, theme_dir, tmp_path):
    def _render(markdown, **extra):
        files = {"publications/publications.toml": SECTION}
        files["publications/p/content.en.md"] = markdown
        files.update(extra)
        root = make_content(files)
        site = load_site(root)
        theme = load_theme(theme_dir, site.settings)
        render_site(site, theme, tmp_path / "out")
        return (tmp_path / "out" / "publications" / "p" / "index.html").read_text("utf-8")

    return _render


def test_a_publication_links_to_its_doi(render):
    html = render(_publication("https://doi.org/10.5281/zenodo.22885603"))
    assert 'href="https://doi.org/10.5281/zenodo.22885603"' in html
    assert 'data-pt-title="DOI"' in html


def test_the_doi_link_opens_safely_in_a_new_tab(render):
    html = render(_publication("10.5281/zenodo.22885603"))
    assert 'rel="noopener noreferrer"' in html


def test_a_publication_without_a_doi_shows_no_doi_link(render):
    html = render("---\ntitle: A paper\ndate: 2026-01-01\nlanguage: en\n---\n")
    assert "doi.org" not in html
