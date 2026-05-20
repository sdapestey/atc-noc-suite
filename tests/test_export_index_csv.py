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


def test_export_rama_solo_in_service(monkeypatch):
    import services.exports as exp

    monkeypatch.setattr(
        exp,
        "consultar_rama_estructura",
        lambda _rama: {
            "TG01-FATC-8-1": [
                {"AID": "105", "OPERADOR": "TASA", "ONT": "O1", "STATUS": "IN SERVICE"},
                {"AID": "106", "OPERADOR": "TASA", "ONT": "O2", "STATUS": "FREE"},
            ],
        },
    )
    out = exp.export_index_query_csv("TG01-RATC-0-000308")
    assert "105" in out
    assert "106" not in out
    assert out.strip().endswith("# resumen,ONT IN SERVICE,1")


def test_export_rama_filtra_operador(monkeypatch):
    import services.exports as exp

    monkeypatch.setattr(
        exp,
        "consultar_rama_estructura",
        lambda _rama: {
            "TG01-FATC-8-1": [
                {"AID": "105", "OPERADOR": "TASA", "ONT": "O1", "STATUS": "IN SERVICE"},
                {"AID": "107", "OPERADOR": "ATC", "ONT": "O3", "STATUS": "IN SERVICE"},
            ],
        },
    )
    out = exp.export_index_query_csv("TG01-RATC-0-000308", operador="TASA")
    assert "105" in out
    assert "107" not in out


def test_export_cto_solo_in_service(monkeypatch):
    import services.exports as exp

    monkeypatch.setattr(
        exp,
        "consultar_cto_estructura",
        lambda _cto: [
            {"AID": "105", "OPERADOR": "TASA", "RAMA": "R1", "ONT": "O1", "STATUS": "IN SERVICE"},
            {"AID": "106", "OPERADOR": "TASA", "RAMA": "R1", "ONT": "O2", "STATUS": "RESERVED"},
        ],
    )
    out = exp.export_index_query_csv("TG01-FATC-8-1")
    assert "105" in out
    assert "106" not in out


def test_export_access_id_no_in_service_sin_fila_datos(monkeypatch):
    import services.exports as exp

    monkeypatch.setattr(
        exp,
        "consultar_access_id_detalle_desde_bajada_inventario",
        lambda _v: {
            "AID": "105",
            "OPERADOR": "TASA",
            "Status": "FREE",
            "CTO": "C1",
            "RAMA": "R1",
            "ONT": "O1",
            "SN": "",
            "fuente_detalle": "bajada_inventario",
        },
    )
    monkeypatch.setattr(exp, "consultar_access_id_baja_o_ausente", lambda _v: {"tipo": "no_existe"})

    out = exp.export_index_query_csv("105")
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    assert lines == ["AID,OPERADOR,Status,CTO,RAMA,ONT,SN,fuente", "# resumen,ONT IN SERVICE,0"]


def test_export_csv_footer_total_in_service(monkeypatch):
    import services.exports as exp

    monkeypatch.setattr(
        exp,
        "consultar_rama_estructura",
        lambda _rama: {
            "TG01-FATC-8-1": [
                {"AID": "105", "OPERADOR": "TASA", "ONT": "O1", "STATUS": "IN SERVICE"},
                {"AID": "106", "OPERADOR": "TASA", "ONT": "O2", "STATUS": "FREE"},
            ],
        },
    )
    out = exp.export_index_query_csv("TG01-RATC-0-000308")
    assert out.strip().endswith("# resumen,ONT IN SERVICE,1")


def test_export_index_csv_filename_todos_ramas():
    import services.exports as exp

    value = "TG01-RATC-0-000308\nTG01-RATC-0-000309\nTG01-RATC-0-000310"
    assert exp.export_index_csv_filename(value) == "Clientes 3 ramas.csv"
    assert exp.export_index_csv_filename(value, operador="ALL") == "Clientes 3 ramas.csv"


def test_export_index_csv_filename_por_operador():
    import services.exports as exp

    value = "TG01-RATC-0-000308\nTG01-RATC-0-000309"
    assert exp.export_index_csv_filename(value, operador="TASA") == "Clientes TASA.csv"


def test_export_index_csv_filename_single_rama():
    import services.exports as exp

    assert exp.export_index_csv_filename("TG01-RATC-0-000308") == "Clientes 1 ramas.csv"
