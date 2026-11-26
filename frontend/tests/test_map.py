"""The AOI map: WKT in the front matter, GeoJSON and MapLibre config out."""

import json

import pytest

from build import (
    ContentError,
    aoi_geojson,
    load_site,
    load_theme,
    map_config,
    parse_wkt,
    render_site,
)

SQUARE = "POLYGON ((-45.1 -15.5, -44.6 -15.5, -44.6 -15.0, -45.1 -15.0, -45.1 -15.5))"


@pytest.fixture
def rendered(fixture_content, theme_dir, tmp_path):
    def _render():
        site = load_site(fixture_content)
        theme = load_theme(theme_dir, site.settings)
        render_site(site, theme, tmp_path / "site")
        return tmp_path / "site"

    return _render


# --------------------------------------------------------------------------
# WKT
# --------------------------------------------------------------------------

def test_a_polygon_becomes_a_geojson_geometry():
    assert parse_wkt(SQUARE) == {
        "type": "Polygon",
        "coordinates": [
            [
                [-45.1, -15.5],
                [-44.6, -15.5],
                [-44.6, -15.0],
                [-45.1, -15.0],
                [-45.1, -15.5],
            ]
        ],
    }


def test_a_polygon_with_a_hole_keeps_both_rings():
    wkt = (
        "POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0), (1 1, 2 1, 2 2, 1 2, 1 1))"
    )
    assert len(parse_wkt(wkt)["coordinates"]) == 2


def test_a_multipolygon_becomes_a_multipolygon():
    wkt = "MULTIPOLYGON (((0 0, 1 0, 1 1, 0 0)), ((5 5, 6 5, 6 6, 5 5)))"
    geometry = parse_wkt(wkt)
    assert geometry["type"] == "MultiPolygon"
    assert len(geometry["coordinates"]) == 2


def test_the_keyword_is_case_insensitive_and_spacing_is_free():
    assert parse_wkt("polygon((0 0,1 0,1 1,0 0))")["type"] == "Polygon"


def test_an_unclosed_ring_is_closed():
    ring = parse_wkt("POLYGON ((0 0, 1 0, 1 1))")["coordinates"][0]
    assert ring[0] == ring[-1]


def test_a_geometry_that_is_not_a_polygon_is_refused():
    with pytest.raises(ContentError, match="POINT"):
        parse_wkt("POINT (1 2)")


def test_malformed_wkt_is_refused():
    with pytest.raises(ContentError, match="aoi_wkt"):
        parse_wkt("POLYGON ((0 0, 1, 1 1, 0 0))")


def test_an_empty_ring_is_refused():
    with pytest.raises(ContentError, match="aoi_wkt"):
        parse_wkt("POLYGON (())")


# --------------------------------------------------------------------------
# the vertex budget
# --------------------------------------------------------------------------

def test_a_ring_within_the_budget_is_left_alone():
    collection = _collection(SQUARE, max_vertices=50)
    assert collection["features"][0]["geometry"] == parse_wkt(SQUARE)


def test_an_oversized_ring_is_thinned_to_the_budget():
    ring = ", ".join(f"{index} 0" for index in range(100)) + ", 0 0"
    collection = _collection(f"POLYGON (({ring}))", max_vertices=10)
    coordinates = collection["features"][0]["geometry"]["coordinates"][0]
    assert len(coordinates) <= 10
    assert coordinates[0] == coordinates[-1]


def test_thinning_never_drops_a_ring_below_a_triangle():
    ring = ", ".join(f"{index} 0" for index in range(60)) + ", 0 0"
    collection = _collection(f"POLYGON (({ring}))", max_vertices=2)
    assert len(collection["features"][0]["geometry"]["coordinates"][0]) == 4


# --------------------------------------------------------------------------
# the feature collection
# --------------------------------------------------------------------------

def test_each_feature_is_keyed_by_the_item_slug(fixture_content):
    section = load_site(fixture_content).sections["publications"]
    collection = aoi_geojson(section, ["en", "pt"], max_vertices=50)
    assert [feature["id"] for feature in collection["features"]] == ["veredas"]


def test_a_feature_carries_its_title_in_every_language(fixture_content):
    section = load_site(fixture_content).sections["publications"]
    properties = aoi_geojson(section, ["en", "pt"], 50)["features"][0]["properties"]
    assert properties["title_en"].startswith("Mapping Veredas")
    assert properties["title_pt"].startswith("Mapping Veredas")
    assert properties["slug"] == "veredas"


def test_the_collection_carries_a_bounding_box(fixture_content):
    section = load_site(fixture_content).sections["publications"]
    assert aoi_geojson(section, ["en"], 50)["bbox"] == [-45.1, -15.5, -44.6, -15.0]


def test_items_without_a_geometry_are_simply_absent(make_content):
    root = make_content(
        {
            "posts/posts.toml": '[section]\nkind = "post"\nmap = true\n',
            "posts/x/content.en.md": (
                "---\ntitle: X\ndate: 2026-01-01\nlanguage: en\n---\n"
            ),
        }
    )
    section = load_site(root).sections["posts"]
    assert aoi_geojson(section, ["en"], 50)["features"] == []


# --------------------------------------------------------------------------
# map configuration
# --------------------------------------------------------------------------

def test_the_tile_key_is_substituted_from_the_environment(fixture_content, monkeypatch):
    monkeypatch.setenv("MAP_TILES_KEY", "secret-123")
    settings = load_site(fixture_content).settings
    assert map_config(settings)["style"] == "https://tiles.example/style.json?key=secret-123"


def test_without_a_key_the_map_falls_back_to_a_plain_background(fixture_content, monkeypatch):
    monkeypatch.delenv("MAP_TILES_KEY", raising=False)
    settings = load_site(fixture_content).settings
    style = map_config(settings)["style"]
    assert isinstance(style, dict)
    assert style["layers"][0]["paint"]["background-color"]


def test_the_paint_settings_reach_the_config(fixture_content, monkeypatch):
    monkeypatch.setenv("MAP_TILES_KEY", "k")
    config = map_config(load_site(fixture_content).settings)
    assert config["line_color"] == "#111111"
    assert config["line_width"] == 1.9


def test_the_base_style_is_a_half_millimetre_black_line(make_content, monkeypatch):
    monkeypatch.setenv("MAP_TILES_KEY", "k")
    root = make_content({})
    config = map_config(load_site(root).settings)
    assert config["line_color"] == "#111111"
    assert config["line_width"] == pytest.approx(1.9, abs=0.05)


# --------------------------------------------------------------------------
# the rendered page
# --------------------------------------------------------------------------

def test_a_mapped_section_writes_its_geojson(rendered, monkeypatch):
    monkeypatch.setenv("MAP_TILES_KEY", "k")
    site = rendered()
    collection = json.loads((site / "publications" / "aois.geojson").read_text("utf-8"))
    assert collection["features"][0]["id"] == "veredas"
    assert not (site / "posts" / "aois.geojson").exists()


def test_the_mapped_page_carries_the_container_and_its_config(rendered, monkeypatch):
    monkeypatch.setenv("MAP_TILES_KEY", "k")
    html = (rendered() / "publications" / "index.html").read_text("utf-8")
    assert 'id="aoi-map"' in html
    assert 'id="aoi-config"' in html
    assert "aois.geojson" in html
    assert "maplibre-gl.mjs" in html


def test_an_unmapped_page_loads_no_map(rendered, monkeypatch):
    monkeypatch.setenv("MAP_TILES_KEY", "k")
    html = (rendered() / "posts" / "index.html").read_text("utf-8")
    assert "maplibre-gl.mjs" not in html
    assert 'id="btn-aoi"' not in html


def test_the_config_json_cannot_break_out_of_its_script_tag(rendered, monkeypatch):
    monkeypatch.setenv("MAP_TILES_KEY", "</script><script>alert(1)</script>")
    html = (rendered() / "publications" / "index.html").read_text("utf-8")
    assert "<script>alert(1)</script>" not in html


def _collection(wkt, max_vertices):
    """One section holding one item with this geometry."""
    import datetime as dt
    from pathlib import Path

    from build import Item, Section, Translation

    here = Path(".")
    item = Item(
        section="publications",
        slug="x",
        source_dir=here,
        primary_language="en",
        translations={
            "en": Translation(
                language="en", title="X", subtitle=None, body="", source=here
            )
        },
        date=dt.date(2026, 1, 1),
        aoi_wkt=wkt,
    )
    section = Section(
        name="publications", kind="publication", source_dir=here, data={}, map=True
    )
    section.items = [item]
    return aoi_geojson(section, ["en"], max_vertices)
