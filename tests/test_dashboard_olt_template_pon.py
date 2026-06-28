from pathlib import Path


def test_dashboard_olt_template_contains_pon_node_builder():
    tpl = Path("templates/dashboard_olt.html").read_text(encoding="utf-8")
    assert "poncount" in tpl
    assert "noc-tools.js" in tpl
    assert "olt-pon-selected-kicker" in tpl
    assert "dashboard-olt.js" in tpl
    assert "dashboard-tree-panel" in tpl
    assert "dashboard-tree-controls" in tpl
    assert "dashboard-metric-pill" in tpl
    assert "site-head--metrics" in tpl
    assert "site-head-meta" in tpl
    assert "bloque.TOTALES.RAMAS" in tpl
