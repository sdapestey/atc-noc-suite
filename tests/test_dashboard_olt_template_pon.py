from pathlib import Path


def test_dashboard_olt_template_contains_pon_node_builder():
    tpl = Path("templates/dashboard_olt.html").read_text(encoding="utf-8")
    assert "buildPonBlockHtml" in tpl
    assert 'data-olt-tree-kind="PON"' in tpl
    assert "data.PONES" in tpl
    assert "RESUMEN_LT" in tpl
    assert "poncount" in tpl
    assert "pon-select" in tpl
    assert "exportarPonesSeleccionados" in tpl
    assert '["PON", "RAMA", "CTO", "ACCESS_ID", "OPERADOR", "ONT"]' in tpl
