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
    assert "Consultando" in html
    assert "NOC Wiki" in html
    assert "suite-index-card" in html
    assert "noc-suite-surface.css" in html
    assert "global-tabs-row" in html
    assert "global-tab--wiki" in html
    assert "global-nav-group" in html
    assert "data-nav-desktop-group" in html
    assert "global-nav-dd-section" in html
    assert 'target="_blank"' in html
    assert "10.90.1.196:6875" in html


def test_dashboard_rama_does_not_include_splash_overlay(client):
    r = client.get("/dashboard/rama", follow_redirects=True)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="noc-splash-overlay"' not in html


def test_splash_static_assets_exist():
    assert Path("static/js/splash.js").is_file()
    assert Path("static/css/splash.css").is_file()
    assert Path("templates/partials/splash_overlay.html").is_file()


def test_splash_skips_on_index_deep_link_query():
    partial = Path("templates/partials/splash_overlay.html").read_text(encoding="utf-8")
    assert "hasDeepLinkIntent" in partial
    assert 'params.get("q")' in partial
    assert 'params.get("rama")' in partial
    assert "noc-splash-title--reveal" in partial
    assert "noc-splash-title-char-in" in Path("static/css/splash.css").read_text(encoding="utf-8")
