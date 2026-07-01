from pathlib import Path


def test_noc_head_includes_theme_bootstrap_and_script():
    tpl = Path("templates/partials/noc_head.html").read_text(encoding="utf-8")
    assert 'localStorage.getItem("theme")' in tpl
    assert "prefers-color-scheme: dark" in tpl
    assert "data-theme" in tpl
    assert "js/theme-toggle.js" in tpl
    assert "js/noc-clock.js" in tpl


def test_noc_topbar_renders_theme_toggle_button():
    tpl = Path("templates/partials/noc_topbar.html").read_text(encoding="utf-8")
    assert "data-theme-toggle" in tpl
    assert "Modo: Dark" in tpl
    assert "data-noc-clock" in tpl
    assert "noc-app-version" not in tpl
    assert "noc_dashboard_credits" not in tpl
    assert "noc-dashboard-credits" not in tpl
    assert "page_attribution" not in tpl
    assert "page-attribution" not in tpl
    assert "Gimenez" not in tpl
    assert "Jeelbert" not in tpl
    assert "motion.div" not in tpl


def test_index_renders_clock_in_topbar(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "data-noc-clock" in html
    assert "noc-app-version" not in html
    for path in ("/", "/dashboard/olt", "/dashboard/camino-optico"):
        html = client.get(path).get_data(as_text=True)
        assert "leaflet@1.9.4" in html, path
        assert "noc-map-tiles.js" in html, path
        assert "leaflet-scroll-guard.js" in html, path


def test_dashboard_pages_have_no_attribution_line(client):
    paths = [
        "/",
        "/dashboard/olt",
        "/dashboard/estadisticas",
        "/dashboard/potencias-historico",
        "/dashboard/radar-degradacion",
        "/dashboard/camino-optico",
    ]
    for path in paths:
        r = client.get(path)
        assert r.status_code == 200, path
        html = r.get_data(as_text=True)
        assert "page-attribution" not in html, path
        assert "page_attribution.html" not in html, path
