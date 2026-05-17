"""export_index_query_csv alineado con búsqueda por Access ID en índice."""

from unittest.mock import patch


def test_export_digit_desde_bajada_inventario(monkeypatch):
    import services.exports as exp

    det = {
        "AID": "105",
        "OPERADOR": "TASA",
        "Status": "IN SERVICE",
        "CTO": "TG01-FATC-8-1",
        "RAMA": "TG01-RATC-0-1",
        "ONT": "ONT-1",
        "SN": "SN123",
        "fuente_detalle": "bajada_inventario",
    }
    monkeypatch.setattr(exp, "consultar_access_id_detalle_desde_bajada_inventario", lambda _v: det)
    monkeypatch.setattr(exp, "consultar_access_id_baja_o_ausente", lambda _v: {"tipo": "no_existe"})

    out = exp.export_index_query_csv("105")
    assert "bajada_inventario" in out
    assert "SN123" in out
    assert "TG01-FATC-8-1" in out


def test_export_digit_baja(monkeypatch):
    import services.exports as exp

    monkeypatch.setattr(exp, "consultar_access_id_detalle_desde_bajada_inventario", lambda _v: None)
    monkeypatch.setattr(
        exp,
        "consultar_access_id_baja_o_ausente",
        lambda _v: {
            "tipo": "baja",
            "AID": "9",
            "OPERADOR": "TASA",
            "fecha_baja_fmt": "01/01/2026",
            "CTO": "C1",
            "ONT": "O1",
            "fuente_baja": "bajas_de_inventario",
        },
    )

    out = exp.export_index_query_csv("9")
    assert "baja" in out
    assert "bajas_de_inventario" in out
    assert "01/01/2026" in out


def test_export_digit_no_existe(monkeypatch):
    import services.exports as exp

    monkeypatch.setattr(exp, "consultar_access_id_detalle_desde_bajada_inventario", lambda _v: None)
    monkeypatch.setattr(
        exp,
        "consultar_access_id_baja_o_ausente",
        lambda _v: {"tipo": "no_existe", "AID": "999"},
    )

    out = exp.export_index_query_csv("999")
    assert "no encontrado" in out.lower() or "ATC" in out


def test_export_alphanumeric_access_id_uses_bajada(monkeypatch):
    """Access ID alfanumérico (VNO) debe usar la misma ruta que el numérico en CSV."""
    import services.exports as exp

    det = {
        "AID": "fes_a5_23",
        "OPERADOR": "ATC",
        "Status": "IN SERVICE",
        "CTO": "SF01-FATC-8-1",
        "RAMA": "SF01-RATC-0-1",
        "ONT": "ONT-x",
        "SN": "SN999",
        "fuente_detalle": "bajada_inventario",
    }
    monkeypatch.setattr(exp, "consultar_access_id_detalle_desde_bajada_inventario", lambda v: det if v == "fes_a5_23" else None)
    monkeypatch.setattr(exp, "consultar_access_id_baja_o_ausente", lambda _v: {"tipo": "no_existe"})

    out = exp.export_index_query_csv("fes_a5_23")
    assert "fes_a5_23" in out
    assert "SN999" in out
    assert "bajada_inventario" in out


@patch("services.exports.consultar_cto_estructura", lambda _cto: [])
def test_export_fatc_still_uses_cto_estructura():
    import services.exports as exp

    out = exp.export_index_query_csv("ES01-FATC-8-1")
    assert "AID" in out or "error" in out


def test_export_multiple_tokens_two_blocks(monkeypatch):
    import services.exports as exp

    def det(aid):
        return {
            "AID": aid,
            "OPERADOR": "TASA",
            "Status": "IN SERVICE",
            "CTO": "TG01-FATC-8-1",
            "RAMA": "TG01-RATC-0-1",
            "ONT": "ONT-1",
            "SN": "SN123",
            "fuente_detalle": "bajada_inventario",
        }

    monkeypatch.setattr(
        exp,
        "consultar_access_id_detalle_desde_bajada_inventario",
        lambda v: det(v) if v in ("105", "106") else None,
    )
    monkeypatch.setattr(exp, "consultar_access_id_baja_o_ausente", lambda _v: {"tipo": "no_existe"})

    out = exp.export_index_query_csv("105, 106")
    assert "# consulta" in out
    assert "105" in out
    assert "106" in out
