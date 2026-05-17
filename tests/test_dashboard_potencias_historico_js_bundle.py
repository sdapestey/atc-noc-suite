from pathlib import Path


def test_dashboard_potencias_historico_uses_external_js_bundle():
    html = Path("templates/dashboard_potencias_historico.html").read_text(encoding="utf-8")
    js = Path("static/js/dashboard-potencias-historico.js").read_text(encoding="utf-8")
    assert "dashboard-potencias-historico.js" in html
    assert "let powerChart = null" not in html
    assert 'function fetchData(' in js
    assert "function resetDashboard(" in js
    assert "function _historicoPanelVisible(" in js
    assert "function mergeSnapshot(" in js
    assert "dashboard-historico-potencias.css" in html
    assert "motion.div" not in html
    assert "motion.div" not in js


def test_historico_css_extracted_from_main_bundle():
    main_css = Path("static/css/devops-dashboard.css").read_text(encoding="utf-8")
    page_css = Path("static/css/dashboard-historico-potencias.css").read_text(encoding="utf-8")
    assert "dashboard-historico-potencias.css" in main_css
    assert ".page-historico-potencias .metrics-grid" in page_css
    assert ".page-historico-potencias .metrics-grid" not in main_css
