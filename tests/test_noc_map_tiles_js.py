from pathlib import Path


def test_noc_map_tiles_uses_carto_only_not_osm_tile_server():
    js = Path("static/js/noc-map-tiles.js").read_text(encoding="utf-8")
    assert "basemaps.cartocdn.com" in js
    assert "rastertiles/voyager" in js
    assert "dark_all" in js
    assert "{y}{r}.png" in js
    assert "tileerror" not in js
    assert "_tryNextFallback" not in js
    assert "tile.openstreetmap.org/{z}" not in js
    assert "openstreetmap.org/copyright" in js
    assert "NocMapTiles" in js
    assert "createLeafletMap" in js
    assert "refreshLeafletMapLayout" in js
    assert "data-theme" in js
    assert "NocMapFullscreen" in js

    fs = Path("static/js/noc-map-fullscreen.js").read_text(encoding="utf-8")
    assert "attachMapFullscreen" in fs
    assert "requestFullscreen" in fs
    assert "noc-map-fs-btn" in fs
