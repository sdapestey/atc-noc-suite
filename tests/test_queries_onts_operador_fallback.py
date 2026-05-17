"""Fallback de operador: OLT sin invocator → aux.bajada_inventario (misma regla que detalle AID)."""


def test_onts_por_cto_coalesce_invocator_desde_bajada():
    from queries import QUERIES

    sql = QUERIES["onts_por_cto"]
    assert "COALESCE(o.invocator_system, b_aid.operatorid)" in sql
    assert "aux.bajada_inventario" in sql


def test_onts_por_rama_coalesce_invocator_desde_bajada():
    from queries import QUERIES

    sql = QUERIES["onts_por_rama"]
    assert "COALESCE(o.invocator_system, b_aid.operatorid)" in sql
    assert "aux.bajada_inventario" in sql
