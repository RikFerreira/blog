"""Copying the theme's static files and the assets that belong to content."""

import pytest

from build import copy_assets, load_site, load_theme, render_site


@pytest.fixture
def built(fixture_content, theme_dir, tmp_path):
    site = load_site(fixture_content)
    theme = load_theme(theme_dir, site.settings)
    out = tmp_path / "site"
    render_site(site, theme, out)
    copy_assets(site, theme, out)
    return out


def test_the_theme_static_files_land_at_the_root(built):
    assert (built / "css" / "styles.css").is_file()
    assert (built / "js" / "site.js").is_file()
    assert (built / "js" / "aoi-map.js").is_file()


def test_an_items_assets_land_beside_its_page(built):
    assert (built / "posts" / "hello-world" / "assets" / "cover.png").is_file()
    assert (built / "publications" / "veredas" / "assets" / "fig.png").is_file()


def test_the_bibliography_is_published_so_it_can_be_linked(built):
    assert (built / "publications" / "veredas" / "cite.bib").is_file()


def test_the_markdown_source_is_not_published(built):
    assert not (built / "posts" / "hello-world" / "content.en.md").exists()
    assert not (built / "posts" / "hello-world" / "content.pt.md").exists()


def test_global_assets_land_under_assets(fixture_content, theme_dir, tmp_path):
    (fixture_content / "assets" / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    try:
        site = load_site(fixture_content)
        theme = load_theme(theme_dir, site.settings)
        out = tmp_path / "site"
        copy_assets(site, theme, out)
        assert (out / "assets" / "favicon.svg").is_file()
    finally:
        (fixture_content / "assets" / "favicon.svg").unlink()


def test_an_unchanged_file_is_not_copied_again(fixture_content, theme_dir, tmp_path):
    site = load_site(fixture_content)
    theme = load_theme(theme_dir, site.settings)
    out = tmp_path / "site"
    copy_assets(site, theme, out)
    target = out / "css" / "styles.css"
    before = target.stat().st_mtime_ns

    copied = copy_assets(site, theme, out)
    assert target.stat().st_mtime_ns == before
    assert target not in copied


def test_a_changed_file_is_copied_again(fixture_content, theme_dir, tmp_path):
    site = load_site(fixture_content)
    theme = load_theme(theme_dir, site.settings)
    out = tmp_path / "site"
    copy_assets(site, theme, out)

    target = out / "css" / "styles.css"
    target.write_text("stale", encoding="utf-8")
    import os

    os.utime(target, (0, 0))

    assert target in copy_assets(site, theme, out)
    assert target.read_text(encoding="utf-8") != "stale"
