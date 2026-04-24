"""consultar_access_id_detalle_desde_bajada_inventario, consultar_access_id_baja_o_ausente e índice (AID)."""
from contextlib import contextmanager


def _fake_db_cursor_bajas_aux(bde_row=None, bi_row=None):
    """Consultas a aux.bajas_de_inventario y aux.bajas_inventario (consultar_access_id_baja_o_ausente)."""

    @contextmanager
    def fake_db():
        class FakeCur:
            def execute(self, sql, params=None):
                self._sql = sql or ""

            def fetchone(self):
                s = self._sql or ""
                if "aux.bajas_de_inventario" in s:
                    return bde_row
                if "aux.bajas_inventario" in s:
                    return bi_row
                return None

        yield FakeCur()

    return fake_db


def _fake_db_cursor_bajada_detalle(bajada_row=None):
    """SELECT desde aux.bajada_inventario (detalle AID)."""

    @contextmanager
    def fake_db():
        class FakeCur:
            def execute(self, sql, params=None):
                self._sql = sql or ""

            def fetchone(self):
                if "aux.bajada_inventario" in self._sql and "bajas_de_inventario" not in self._sql:
                    return bajada_row
                return None

        yield FakeCur()

    return fake_db


def test_consultar_access_id_detalle_desde_bajada_inventario_con_fila(monkeypatch):
    from services import inventory as inv

    dt = __import__("datetime").datetime(2026, 4, 22, 14, 30)
    row = (
        1001,
        dt,
        None,
        "SF01-FATC-8-200189",
        None,
        "BA_OLTA_SF01_01-1-2-3:1-1",
        "SF01-RATC-0-000308",
        "IN SERVICE",
        "ALCLF00ABCD12",
    )
    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_bajada_detalle(bajada_row=row))
    out = inv.consultar_access_id_detalle_desde_bajada_inventario("1058516041")
    assert out is not None
    assert out["AID"] == "1058516041"
    assert out["OPERADOR"] == "TASA"
    assert out["CTO"] == "SF01-FATC-8-200189"
    assert out["RAMA"] == "SF01-RATC-0-000308"
    assert out["Status"] == "IN SERVICE"
    assert "BA_OLTA_SF01_01-1-2-3" in out["ONT"]
    assert out["SN"] == "ALCLF00ABCD12"
    assert out.get("fuente_detalle") == "bajada_inventario"


def test_consultar_access_id_detalle_desde_bajada_prefiere_cm_description(monkeypatch):
    from services import inventory as inv

    row = (
        1001,
        None,
        None,
        "HEXCTO",
        "TG01-FATC-8-100987",
        None,
        None,
        None,
        None,
    )
    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_bajada_detalle(bajada_row=row))
    out = inv.consultar_access_id_detalle_desde_bajada_inventario("1")
    assert out["CTO"] == "TG01-FATC-8-100987"
    assert out["Status"] == "Registro aux.bajada_inventario"
    assert out["SN"] == "—"


def test_consultar_access_id_detalle_desde_bajada_sin_fila(monkeypatch):
    from services import inventory as inv

    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_bajada_detalle(bajada_row=None))
    assert inv.consultar_access_id_detalle_desde_bajada_inventario("999") is None


def test_consultar_access_id_baja_o_ausente_no_existe(monkeypatch):
    from services import inventory as inv

    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_bajas_aux(bde_row=None, bi_row=None))
    out = inv.consultar_access_id_baja_o_ausente("9999999999")
    assert out["tipo"] == "no_existe"
    assert out["AID"] == "9999999999"


def test_consultar_access_id_baja_o_ausente_solo_bajas_de_inventario(monkeypatch):
    from services import inventory as inv

    bde_row = (
        "1001",
        "2026-04-23",
        "2024-04-24 14:06:40",
        None,
        "04C009EAC05D84",
        "TG01-FATC-8-100987",
        "BA_OLTA_SF01_04:1-1-5-9-5:1-1",
    )
    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_bajas_aux(bde_row=bde_row, bi_row=None))
    out = inv.consultar_access_id_baja_o_ausente("1053492422")
    assert out["tipo"] == "baja"
    assert out.get("fuente_baja") == "bajas_de_inventario"
    assert out["OPERADOR"] == "TASA"
    assert out["fecha_baja_fmt"] == "23/04/2026"
    assert out.get("CTO") == "TG01-FATC-8-100987"


def test_consultar_access_id_baja_o_ausente_solo_bajas_inventario(monkeypatch):
    from services import inventory as inv

    bi_row = (
        "1001",
        "2026-04-23",
        None,
        None,
        "04C009EAC05D84",
        "TG01-FATC-8-100987",
        "BA_OLTA_SF01_04:1-1-5-9-5:1-1",
    )
    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_bajas_aux(bde_row=None, bi_row=bi_row))
    out = inv.consultar_access_id_baja_o_ausente("1053492422")
    assert out["tipo"] == "baja"
    assert out.get("fuente_baja") == "bajas_inventario"
    assert out["OPERADOR"] == "TASA"
    assert out["fecha_baja_fmt"] == "23/04/2026"


def test_consultar_access_id_baja_o_ausente_prioriza_bajas_de_sobre_bajas_inventario(monkeypatch):
    from services import inventory as inv

    bde_row = (
        "1001",
        "2026-06-01",
        None,
        None,
        "CTO-DE",
        None,
        None,
    )
    bi_row = (
        "3001",
        "2026-01-01",
        None,
        None,
        "CTO-BI",
        None,
        None,
    )
    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_bajas_aux(bde_row=bde_row, bi_row=bi_row))
    out = inv.consultar_access_id_baja_o_ausente("1")
    assert out["tipo"] == "baja"
    assert out.get("fuente_baja") == "bajas_de_inventario"
    assert out.get("CTO") == "CTO-DE"


def test_consultar_access_id_baja_o_ausente_bajas_de_cto_fallback_sin_cm(monkeypatch):
    from services import inventory as inv

    bde_row = (
        "1001",
        "2026-04-23",
        None,
        None,
        "04HEXONLY",
        "",
        None,
    )
    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_bajas_aux(bde_row=bde_row, bi_row=None))
    out = inv.consultar_access_id_baja_o_ausente("999888")
    assert out["tipo"] == "baja"
    assert out.get("fuente_baja") == "bajas_de_inventario"
    assert out.get("CTO") == "04HEXONLY"


def test_consultar_access_id_bajas_de_sin_cm_description_reintento(monkeypatch):
    """Fallo con cm_description y reintento sin columna."""
    from services import inventory as inv

    plain_row = (
        "1001",
        "2026-04-23",
        None,
        None,
        "ONLYCTO",
        "ONT-X:1-1",
    )

    @contextmanager
    def fake_db():
        class FakeCur:
            def execute(self, sql, params=None):
                self._sql = sql or ""
                if "bajas_de_inventario" in self._sql and "cm_description" in self._sql:
                    raise RuntimeError("column cm_description does not exist")

            def fetchone(self):
                s = self._sql or ""
                if "bajas_de_inventario" in s and "cm_description" not in s:
                    return plain_row
                if "bajas_inventario" in s:
                    return None
                return None

        yield FakeCur()

    monkeypatch.setattr(inv, "db_cursor", fake_db)
    out = inv.consultar_access_id_baja_o_ausente("111")
    assert out["tipo"] == "baja"
    assert out["fuente_baja"] == "bajas_de_inventario"
    assert out["CTO"] == "ONLYCTO"


def test_index_post_aid_detalle_desde_bajada(client, monkeypatch):
    import web.routes as routes

    det = {
        "AID": "1058516041",
        "OPERADOR": "TASA",
        "Status": "IN SERVICE",
        "CTO": "TG01-FATC-8-1",
        "RAMA": "TG01-RATC-0-1",
        "ONT": "ONT-1",
        "SN": "SN1",
        "TX": None,
        "RX": None,
        "fuente_detalle": "bajada_inventario",
    }
    monkeypatch.setattr(routes, "consultar_access_id_detalle_desde_bajada_inventario", lambda _aid: det)
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "1058516041"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "(aux.bajada_inventario)" in html
    assert "<th>AID</th>" in html
    assert "1058516041" in html
    assert "Access ID dado de baja" not in html


def test_index_post_aid_baja_banner(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_access_id_detalle_desde_bajada_inventario", lambda _aid: None)
    monkeypatch.setattr(
        routes,
        "consultar_access_id_baja_o_ausente",
        lambda _aid: {
            "tipo": "baja",
            "fuente_baja": "bajas_de_inventario",
            "AID": "1058516041",
            "OPERADOR": "TASA",
            "fecha_baja_fmt": "22/04/2026",
            "CTO": "X-CTO",
            "ONT": "ONT-1",
        },
    )

    r = client.post("/", data={"value": "1058516041"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Access ID dado de baja" in html
    assert "fue dado de baja el" in html
    assert "1058516041" in html
    assert "22/04/2026" in html
    assert "TASA" in html


def test_index_post_aid_baja_banner_bajas_de_inventario(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_access_id_detalle_desde_bajada_inventario", lambda _aid: None)
    monkeypatch.setattr(
        routes,
        "consultar_access_id_baja_o_ausente",
        lambda _aid: {
            "tipo": "baja",
            "fuente_baja": "bajas_de_inventario",
            "AID": "1052501426",
            "OPERADOR": "TASA",
            "fecha_baja_fmt": "23/04/2026",
            "CTO": "CTO-1",
            "ONT": "ONT-9",
        },
    )

    r = client.post("/", data={"value": "1052501426"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Access ID dado de baja" in html
    assert "fue dado de baja el" in html
    assert "TASA" in html
    assert "23/04/2026" in html
    assert "1052501426" in html


def test_index_post_aid_no_existe_banner(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_access_id_detalle_desde_bajada_inventario", lambda _aid: None)
    monkeypatch.setattr(
        routes,
        "consultar_access_id_baja_o_ausente",
        lambda _aid: {"tipo": "no_existe", "AID": "999"},
    )

    r = client.post("/", data={"value": "999"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "no se encuentra en los sistemas de ATC" in html
    assert ">999<" in html or "999" in html


def test_index_post_aid_ok_sin_banner_baja(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_access_id_detalle_desde_bajada_inventario",
        lambda _aid: {
            "AID": "105",
            "OPERADOR": "TASA",
            "Status": "IN SERVICE",
            "CTO": "TG01-FATC-8-100987",
            "RAMA": "TG01-RATC-0-000308",
            "ONT": "BA_OLTA_TG01_02-2-15-8",
            "SN": "04EDFBADD5F81",
            "TX": None,
            "RX": None,
            "fuente_detalle": "bajada_inventario",
        },
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "105"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Access ID dado de baja" not in html
    assert "<th>AID</th>" in html


def test_index_post_aid_banner_baja_sin_detalle_bajada(client, monkeypatch):
    """Sin fila en bajada_inventario y baja en bajas_de: solo banner."""
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_access_id_detalle_desde_bajada_inventario", lambda _aid: None)
    monkeypatch.setattr(
        routes,
        "consultar_access_id_baja_o_ausente",
        lambda _aid: {
            "tipo": "baja",
            "fuente_baja": "bajas_de_inventario",
            "AID": "1052505137",
            "OPERADOR": "DIRECTV",
            "fecha_baja_fmt": "01/05/2026",
            "CTO": None,
            "ONT": None,
        },
    )

    r = client.post("/", data={"value": "1052505137"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Access ID dado de baja" in html
    assert "DIRECTV" in html
    assert "<th>AID</th>" not in html


def test_index_post_aid_bajada_muestra_tabla_aunque_haya_baja_aux(client, monkeypatch):
    """Con fila en bajada_inventario se muestra detalle aux; no se aplica el banner de baja."""
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_access_id_detalle_desde_bajada_inventario",
        lambda _aid: {
            "AID": "999001",
            "OPERADOR": "TASA",
            "Status": "Registro aux.bajada_inventario",
            "CTO": "TG01-FATC-8-1",
            "RAMA": "TG01-RATC-0-1",
            "ONT": "ONT",
            "SN": "SN",
            "TX": None,
            "RX": None,
            "fuente_detalle": "bajada_inventario",
        },
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "999001"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Access ID dado de baja" not in html
    assert "<th>AID</th>" in html
    assert "999001" in html


def test_index_post_alias_srvc_loc_ok(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_access_id_desde_alias",
        lambda _alias: {
            "AID": "1058516041",
            "OPERADOR": "METROTEL",
            "Status": "IN SERVICE",
            "CTO": "TG01-FATC-8-1",
            "RAMA": "TG01-RATC-0-1",
            "ONT": "SRVC_LOC_2157",
            "SN": "ALCLF00ABCD12",
            "TX": None,
            "RX": None,
            "fuente_detalle": "alias_inventario",
        },
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "Srvc_loc_2157"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<th>AID</th>" in html
    assert "1058516041" in html
    assert "Access ID dado de baja" not in html


def test_index_post_alias_res_mt_ok_case_insensitive(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_access_id_desde_alias",
        lambda _alias: {
            "AID": "1057770001",
            "OPERADOR": "IPLAN",
            "Status": "IN SERVICE",
            "CTO": "SF01-FATC-8-200189",
            "RAMA": "SF01-RATC-0-000308",
            "ONT": "RES_MT_172",
            "SN": "HWTCABC12345",
            "TX": None,
            "RX": None,
            "fuente_detalle": "alias_inventario",
        },
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "res_mt_172"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<th>AID</th>" in html
    assert "1057770001" in html


def test_index_post_alias_no_existe_banner(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_access_id_desde_alias", lambda _alias: None)

    r = client.post("/", data={"value": "Srvc_loc_999999"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Access ID no encontrado." in html
    assert "Srvc_loc_999999" in html


def test_index_post_alias_res_ip_ok(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_access_id_desde_alias",
        lambda _alias: {
            "AID": "1058880001",
            "OPERADOR": "IPLAN",
            "Status": "IN SERVICE",
            "CTO": "TG01-FATC-8-100987",
            "RAMA": "TG01-RATC-0-000308",
            "ONT": "RES_IP_61",
            "SN": "HWTCABC00061",
            "TX": None,
            "RX": None,
            "fuente_detalle": "alias_inventario",
        },
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "RES_IP_61"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<th>AID</th>" in html
    assert "1058880001" in html
