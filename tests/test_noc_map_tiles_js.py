from pathlib import Path


def test_noc_map_tiles_switch_osm_and_carto_dark():
    js = Path("static/js/noc-map-tiles.js").read_text(encoding="utf-8")
    assert "tile.openstreetmap.org" in js
    assert "basemaps.cartocdn.com" in js and "dark_all" in js
    assert "NocMapTiles" in js
    assert "data-theme" in js
