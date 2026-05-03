"""Splash de bienvenida solo en índice (/)."""

from pathlib import Path


def test_index_includes_splash_partial(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="noc-splash-overlay"' in html
    assert "noc-splash-inner" in html
    assert "splash.js" in html
    assert "splash.css" in html


def test_dashboard_rama_does_not_include_splash_overlay(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_rama_bundle",
        lambda: {"bloques": [], "totales": {"RAMAS": 0, "CTO": 0, "ONT": 0}},
    )
    r = client.get("/dashboard/rama")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="noc-splash-overlay"' not in html


def test_splash_static_assets_exist():
    assert Path("static/js/splash.js").is_file()
    assert Path("static/css/splash.css").is_file()
    assert Path("templates/partials/splash_overlay.html").is_file()
