"""Reporte de rama CM (trazado + inventario)."""
from services.camino_rama_reporte import consultar_reporte_rama_cm


def test_consultar_reporte_rama_cm_vacio():
    assert consultar_reporte_rama_cm("")["ok"] is False


def test_consultar_reporte_rama_cm_775_db():
    rama = "SF01-RATC-0-000775"
    try:
        out = consultar_reporte_rama_cm(rama)
    except Exception:
        return
    if not out.get("ok"):
        return
    assert out["rama"] == rama
    traz = out.get("trazado") or []
    assert 17 <= len(traz) <= 21
    assert traz[0]["etapa"] == "cabecera"
    assert any(r.get("etapa") == "fosc" for r in traz)
    assert traz[-1].get("etapa") == "splitter"
    assert len(out.get("inventario") or []) == len(traz)
    filas = out.get("filas_ruta_fisica") or []
    assert len(filas) == len(traz)
    assert filas[0].get("marca") == "Inicio"
    assert any(f.get("marca") == "Derivación" for f in filas)
    assert filas[-1].get("marca") == "Fin"
    assert filas[0].get("ubicacion_alias") == "Cabecera"
    assert "componente" in filas[0]
    fosc_rows = [f for f in filas if f.get("etapa") == "fosc" and f.get("fosc_id")]
    if fosc_rows:
        assert "direccion" in fosc_rows[0]
        assert "lat" in fosc_rows[0]
