from pathlib import Path


def test_leaflet_scroll_guard_exports_activation_helpers():
    js = Path("static/js/leaflet-scroll-guard.js").read_text(encoding="utf-8")
    assert "scrollWheelZoom: false" in js
    assert "NocLeafletMap" in js
    assert "attachScrollActivation" in js
    assert "baseMapOptions" in js
    assert "pointerdown" in js
