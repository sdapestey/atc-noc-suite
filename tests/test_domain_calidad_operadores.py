"""Operadores del dashboard Calidad Inventario (fuente única en domain)."""
from services.domain import (
    CALIDAD_OPERATORS,
    all_calidad_operator_member_ids,
    calidad_operator_label,
    calidad_operator_member_ids,
    canonical_calidad_operator_id,
)


def test_calidad_operators_count_and_labels():
    assert len(CALIDAD_OPERATORS) == 6
    labels = [op["label"] for op in CALIDAD_OPERATORS]
    assert "TASA" in labels
    assert "ATC" in labels


def test_canonical_maps_alias_vnos():
    assert canonical_calidad_operator_id("2805") == "2800"
    assert canonical_calidad_operator_id("4010") == "4000"
    assert canonical_calidad_operator_id("963") == "962"
    assert canonical_calidad_operator_id("9999") == ""


def test_all_member_ids_includes_aliases():
    mids = all_calidad_operator_member_ids()
    assert "2800" in mids and "2805" in mids
    assert "4000" in mids and "4010" in mids
    assert "962" in mids and "963" in mids


def test_calidad_operator_label():
    assert calidad_operator_label("") == "Todos"
    assert calidad_operator_label("2800") == "ATC"
    assert calidad_operator_label("unknown") == "unknown"


def test_dashboard_reexports_operators():
    import services.dashboard_calidad_inventario as calidad

    assert calidad.OPERATORS is CALIDAD_OPERATORS
    atc = next(o for o in CALIDAD_OPERATORS if o["id"] == "2800")
    assert "2806" in calidad_operator_member_ids(atc)
