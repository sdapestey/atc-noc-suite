"""Consulta masiva: paralelismo por CTO con ``carga_masiva``."""

from services import inventory as inv


def test_potencias_grupos_cto_paralelo_carga_masiva_keyword(monkeypatch):
    """``executor.submit`` debe pasar ``carga_masiva=`` (no posicional)."""
    seen = []

    def fake_filas(rows, *, carga_masiva=False):
        seen.append(carga_masiva)
        aid = rows[0][0]
        return [{"AID": str(aid), "TX": 1.0, "RX": -20.0}]

    monkeypatch.setattr(inv, "_potencias_desde_filas_ont_cto", fake_filas)

    rows = [
        (101, "IN SERVICE", "CTO-A", "RAMA", "obj1", "ui1", "sn1", 1),
        (102, "IN SERVICE", "CTO-B", "RAMA", "obj2", "ui2", "sn2", 1),
    ]
    out = inv._potencias_desde_grupos_cto_paralelo(rows, carga_masiva=True)
    assert len(out) == 2
    assert seen == [True, True]
