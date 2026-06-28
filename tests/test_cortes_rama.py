def test_parse_pon_from_alarm_resource_ct():
    import altiplano

    out = altiplano._parse_pon_from_alarm_resource(
        "interface:BA_OLTA_TG02_02.LT13:CT_BA_OLTA_TG02_02-13-3_3_GPON"
    )
    assert out is not None
    assert out["olt"] == "BA_OLTA_TG02_02"
    assert out["lt"] == "13"
    assert out["pon"] == "3"
    assert out["pon_key"] == "BA_OLTA_TG02_02-13-3"
    assert out["lt_name"] == "BA_OLTA_TG02_02.LT13"


def test_parse_pon_from_alarm_analyzer_formats():
    """Formatos reales del Alarm Analyzer (guion ``-`` antes del sufijo CT)."""
    import altiplano

    cases = [
        (
            "interface:BA_OLTA_SI02_01.LT1:CT_BA_OLTA_SI02_01-1-1-1_GPON",
            "BA_OLTA_SI02_01-1-1",
        ),
        (
            "interface:BA_OLTA_TG01_01.LT10:CT_BA_OLTA_TG01_01-10-13-13_GPON",
            "BA_OLTA_TG01_01-10-13",
        ),
        (
            "interface:BA_OLTA_TG02_02.LT13:CT_BA_OLTA_TG02_02-13-3-3_GPON",
            "BA_OLTA_TG02_02-13-3",
        ),
        (
            "CT_BA_OLTA_SF01_04-4-16-16_GPON",
            "BA_OLTA_SF01_04-4-16",
        ),
        (
            "CT_BA_OLTA_SM02_05-2-11-11_GPON",
            "BA_OLTA_SM02_05-2-11",
        ),
        (
            "interface:BA_OLTA_TG02_02.LT13:CT_BA_OLTA_TG02_02-13-3_3_GPON",
            "BA_OLTA_TG02_02-13-3",
        ),
    ]
    for resource, expected_key in cases:
        out = altiplano._parse_pon_from_alarm_resource(resource)
        assert out is not None, resource
        assert out["pon_key"] == expected_key, (resource, out["pon_key"])


def test_parse_pon_from_alarm_resource_tg01_gui():
    import altiplano

    resource = (
        "interface:BA_OLTA_TG01_01.LT10:"
        "CT_BA_OLTA_TG01_01-10-13-13_GPON"
    )
    out = altiplano._parse_pon_from_alarm_resource(resource)
    assert out is not None
    assert out["pon_key"] == "BA_OLTA_TG01_01-10-13"
    assert out["lt"] == "10"
    assert out["pon"] == "13"


def test_parse_pon_from_alarm_resource_v7_pon():
    import altiplano

    out = altiplano._parse_pon_from_alarm_resource(
        "",
        raw="interface=v7~BA_OLTA_TG01_01-10-13_GPON",
    )
    assert out is not None
    assert out["pon_key"] == "BA_OLTA_TG01_01-10-13"


def test_es_corte_pon_masivo_losi_sin_for_all_onus():
    import altiplano

    text = (
        "Event=loss of signal on Channel Termination due to "
        "LOSi/LOBi detected for all ONUs"
    )
    assert altiplano._es_corte_pon_masivo(
        text=text, alarm_type="channel-termination-loss-of-signal"
    )
    assert altiplano._es_corte_pon_masivo(
        text="Event=loss of signal on Channel Termination due to LOSi/LOBi",
        alarm_type="channel-termination-loss-of-signal",
    )


def test_clasificar_causa_corte_pon():
    import altiplano

    assert (
        altiplano._clasificar_causa_corte_pon(
            "Event=loss of signal on Channel Termination due to Dying Gasp detected for all ONUs"
        )
        == "DYING_GASP"
    )
    assert (
        altiplano._clasificar_causa_corte_pon(
            "Event=loss of signal on Channel Termination due to LOSi/LOBi detected for all ONUs"
        )
        == "LOSI_LOBI"
    )


def test_build_alarmas_corte_pon_search_query():
    import altiplano
    from datetime import date

    q = altiplano._build_alarmas_corte_pon_search_query(page_from=10, page_size=50)
    assert q["from"] == 10
    assert q["size"] == 50
    must = q["query"]["bool"]["must"]
    status_should = must[0]["bool"]["should"]
    assert any(s.get("term", {}).get("alarmStatus") == "Active" for s in status_should)
    assert must[1] == {
        "match_phrase": {"alarmType": altiplano._CORTE_PON_ALARM_TYPE}
    }
    assert len(must) == 2

    q_day = altiplano._build_alarmas_corte_pon_search_query(
        estado="cleared", raised_on=date(2026, 6, 5)
    )
    must_day = q_day["query"]["bool"]["must"]
    assert len(must_day) == 3
    rng = must_day[2]["range"]["raisedTime"]
    assert rng["gte"] == "2026-06-05T03:00:00.000Z"
    assert rng["lt"] == "2026-06-06T03:00:00.000Z"


def test_art_day_raised_time_bounds():
    import altiplano
    from datetime import date

    gte, lt = altiplano._art_day_raised_time_bounds(date(2026, 6, 5))
    assert gte == "2026-06-05T03:00:00.000Z"
    assert lt == "2026-06-06T03:00:00.000Z"


def test_build_alarmas_corte_pon_search_query_todas():
    import altiplano

    q = altiplano._build_alarmas_corte_pon_search_query(estado="todas")
    status_should = q["query"]["bool"]["must"][0]["bool"]["should"]
    statuses = {s.get("term", {}).get("alarmStatus") for s in status_should}
    assert statuses >= {"Active", "Cleared"}


def test_inp_alarm_search_url_sin_index_para_cleared(monkeypatch):
    import altiplano

    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _ne: ("10.0.0.1", "32443", "inp-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano, "get_altiplano_operator_credentials", lambda _ne: ("u", "p")
    )
    activas = altiplano._inp_alarm_search_url(estado="activas")
    cleared = altiplano._inp_alarm_search_url(estado="cleared")
    assert activas
    assert cleared
    assert "index=alarms-active" in activas[0]
    assert "index=" not in cleared[0]


def test_parse_alarmas_corte_pon_search_body_cleared():
    import altiplano

    body = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "alarmStatus": "Cleared",
                        "alarmSeverity": "major",
                        "alarmType": "channel-termination-loss-of-signal",
                        "raisedTime": "2026-06-09T08:00:00.000Z",
                        "clearedTime": "2026-06-09T09:00:00.000Z",
                        "alarmResourceUiName": "CT_BA_OLTA_SF01_02-1-2_2_GPON",
                        "alarmText": "for all ONUs",
                    }
                }
            ]
        }
    }
    out = altiplano._parse_alarmas_corte_pon_search_body(
        body, allowed_statuses=frozenset({"cleared"})
    )
    assert len(out) == 1
    assert out[0]["status"] == "Cleared"
    assert out[0]["cleared"] == "2026-06-09T09:00:00.000Z"


def test_obtener_alarmas_corte_pon_activas_filtra_y_pagina(monkeypatch):
    import altiplano

    pages = [
        {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "alarmStatus": "Active",
                            "alarmSeverity": "major",
                            "alarmType": "channel-termination-loss-of-signal",
                            "raisedTime": "2026-06-09T10:00:00.000Z",
                            "alarmResourceUiName": (
                                "interface:BA_OLTA_SF01_02.LT1:"
                                "CT_BA_OLTA_SF01_02-1-2_2_GPON"
                            ),
                            "alarmText": (
                                "Event=loss of signal on Channel Termination due to "
                                "LOSi/LOBi detected for all ONUs"
                            ),
                        }
                    }
                ]
            }
        },
        {"hits": {"hits": []}},
    ]

    def fake_post(url, auth_url, payload, **kwargs):
        idx = payload.get("from", 0)
        return pages[0] if idx == 0 else pages[1]

    monkeypatch.setattr(altiplano, "_http_post_altiplano_json", fake_post)
    def fake_url(**_kw):
        return ("https://h/search?index=alarms-active", "https://h/auth", "u", "p")

    monkeypatch.setattr(altiplano, "_inp_alarm_search_url", fake_url)

    out = altiplano.obtener_alarmas_corte_pon_activas()
    assert len(out) == 1
    assert out[0]["causa"] == "LOSI_LOBI"
    assert out[0]["pon_key"] == "BA_OLTA_SF01_02-1-2"


def test_build_grupos_sitio_lt():
    from services.cortes_rama import _build_grupos_sitio_lt

    items = [
        {
            "principal": "Tigre",
            "lt_name": "BA_OLTA_TG02_02.LT13",
            "olt": "BA_OLTA_TG02_02",
            "lt": "13",
            "causa": "LOSI_LOBI",
            "ont_total": 5,
            "vnos": {"TASA": 3, "DIRECTV": 2},
            "ramas": ["TG02-RATC-0-001"],
            "pon_key": "a",
        },
        {
            "principal": "Tigre",
            "lt_name": "BA_OLTA_TG02_02.LT13",
            "olt": "BA_OLTA_TG02_02",
            "lt": "13",
            "causa": "DYING_GASP",
            "ont_total": 2,
            "vnos": {"TASA": 2},
            "ramas": ["TG02-RATC-0-002"],
            "pon_key": "b",
        },
    ]
    grupos = _build_grupos_sitio_lt(items)
    assert len(grupos) == 1
    assert grupos[0]["cortes"] == 2
    assert grupos[0]["ont_total"] == 7
    assert grupos[0]["losi"] == 1
    assert grupos[0]["dying"] == 1
    assert grupos[0]["olt_count"] == 1
    assert set(grupos[0]["ramas"]) == {"TG02-RATC-0-001", "TG02-RATC-0-002"}


def test_batch_inventario_por_pon_keys(monkeypatch):
    from services import cortes_rama as cr

    class FakeCur:
        def execute(self, _q, params):
            self._params = params

        def fetchall(self):
            return [
                ("BA_OLTA_TG02_02-13-3-18", "TG02-RATC-0-001047", "CTO-A", 1001),
                ("BA_OLTA_TG02_02:1-1-13-3-5", "TG02-RATC-0-001048", "CTO-B", 3001),
                ("BA_OLTA_TG02_02-13-3-99", "TG02-FATC-8-100987", "CTO-C", 1001),
            ]

    class FakeCtx:
        def __enter__(self):
            return FakeCur()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cr, "db_cursor", lambda: FakeCtx())
    out = cr._batch_inventario_por_pon_keys(["BA_OLTA_TG02_02-13-3"])
    row = out["BA_OLTA_TG02_02-13-3"]
    assert set(row["ramas_ratc"]) == {"TG02-RATC-0-001047", "TG02-RATC-0-001048"}
    assert row["ramas_fatc"] == ["TG02-FATC-8-100987"]
    assert row["ont_total"] == 3
    assert row["cto_count"] == 3
    assert row["vnos"]["TASA"] == 2
    assert row["vnos"]["DIRECTV"] == 1


def test_merge_ramas_display_prefiere_ratc():
    from services.cortes_rama import _merge_ramas_display

    ratcs = {"TG02-RATC-0-001"}
    fatcs = {"TG02-FATC-8-1"}
    assert _merge_ramas_display(ratcs, fatcs) == ["TG02-RATC-0-001"]
    assert _merge_ramas_display(set(), fatcs) == ["TG02-FATC-8-1"]


def test_batch_inventario_mapea_vno_por_id_numerico_texto(monkeypatch):
    from services import cortes_rama as cr

    class FakeCur:
        def execute(self, _q, params):
            self._params = params

        def fetchall(self):
            return [
                ("BA_OLTA_TG02_03-11-16-1", "TG02-RATC-0-001", "4000"),
                ("BA_OLTA_TG02_03-11-16-2", "TG02-RATC-0-001", "2800"),
            ]

    class FakeCtx:
        def __enter__(self):
            return FakeCur()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cr, "db_cursor", lambda: FakeCtx())
    out = cr._batch_inventario_por_pon_keys(["BA_OLTA_TG02_03-11-16"])
    row = out["BA_OLTA_TG02_03-11-16"]
    assert row["vnos"]["METROTEL"] == 1
    assert row["vnos"]["ATC"] == 1


def test_batch_inventario_usa_path_atc_sin_patron_ratc(monkeypatch):
    from services import cortes_rama as cr

    class FakeCur:
        def execute(self, _q, params):
            self._params = params

        def fetchall(self):
            return [
                ("BA_OLTA_TG02_03-11-16-1", "TG02-CUSTOM-PATH-001", 1001),
                ("BA_OLTA_TG02_03-11-16-2", "TG02-CUSTOM-PATH-001", 1001),
            ]

    class FakeCtx:
        def __enter__(self):
            return FakeCur()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cr, "db_cursor", lambda: FakeCtx())
    out = cr._batch_inventario_por_pon_keys(["BA_OLTA_TG02_03-11-16"])
    row = out["BA_OLTA_TG02_03-11-16"]
    assert row["ramas"] == ["TG02-CUSTOM-PATH-001"]
    assert row["ont_total"] == 2


def test_cortes_rama_uncached_enriquece(monkeypatch):
    from services import cortes_rama as cr

    monkeypatch.setattr(
        cr,
        "obtener_alarmas_corte_pon",
        lambda estado="activas", raised_on=None: [
            {
                "severity": "major",
                "status": "Active",
                "raised": "2026-06-09T10:00:00.000Z",
                "resource": "interface:BA_OLTA_TG02_02.LT13:CT_BA_OLTA_TG02_02-13-3_3_GPON",
                "text": "Dying Gasp for all ONUs",
                "olt": "BA_OLTA_TG02_02",
                "lt": "13",
                "pon": "3",
                "lt_name": "BA_OLTA_TG02_02.LT13",
                "pon_key": "BA_OLTA_TG02_02-13-3",
                "pon_label": "PON 3",
                "causa": "DYING_GASP",
                "main_device": "BA_OLTA_TG02_02",
            }
        ],
    )
    monkeypatch.setattr(
        cr,
        "_batch_inventario_por_pon_keys",
        lambda _keys: {
            "BA_OLTA_TG02_02-13-3": {
                "ramas": ["TG02-RATC-0-001047"],
                "ramas_ratc": ["TG02-RATC-0-001047"],
                "ramas_fatc": [],
                "ramas_count": 1,
                "ont_total": 12,
                "vnos": {"TASA": 8, "DIRECTV": 4},
                "vno_list": [
                    {"vno": "TASA", "count": 8},
                    {"vno": "DIRECTV", "count": 4},
                ],
            }
        },
    )

    payload = cr._cortes_rama_uncached()
    assert payload["ok"] is True
    assert payload["totales"]["TOTAL"] == 1
    assert payload["totales"]["CLIENTES_AFECTADOS"] == 12
    assert payload["items"][0]["ont_total"] == 12
    assert payload["items"][0]["vno_list"][0]["vno"] == "TASA"
    assert sum(v["count"] for v in payload["vno_resumen"]) == 12
    assert len(payload["grupos"]) == 1
    assert payload["grupos"][0]["ont_total"] == 12


def test_cortes_rama_no_filtra_por_ultimo_sitio_sin_param(monkeypatch):
    """El bucle de enriquecimiento no debe pisar el parámetro ``principal`` del filtro."""
    from services import cortes_rama as cr

    monkeypatch.setattr(
        cr,
        "obtener_alarmas_corte_pon",
        lambda estado="activas", raised_on=None: [
            {
                "severity": "major",
                "status": "Active",
                "raised": "2026-06-09T16:00:00.000Z",
                "resource": "interface:BA_OLTA_TG01_01.LT10:CT_BA_OLTA_TG01_01-10-13_13_GPON",
                "text": "LOSi for all ONUs",
                "olt": "BA_OLTA_TG01_01",
                "lt": "10",
                "pon": "13",
                "lt_name": "BA_OLTA_TG01_01.LT10",
                "pon_key": "BA_OLTA_TG01_01-10-13",
                "pon_label": "PON 13",
                "causa": "LOSI_LOBI",
                "main_device": "BA_OLTA_TG01_01",
            },
            {
                "severity": "major",
                "raised": "2026-06-09T15:00:00.000Z",
                "resource": "interface:BA_OLTA_SI02_01.LT1:CT_BA_OLTA_SI02_01-1-1_1_GPON",
                "text": "Dying Gasp for all ONUs",
                "olt": "BA_OLTA_SI02_01",
                "lt": "1",
                "pon": "1",
                "lt_name": "BA_OLTA_SI02_01.LT1",
                "pon_key": "BA_OLTA_SI02_01-1-1",
                "pon_label": "PON 1",
                "causa": "DYING_GASP",
                "main_device": "BA_OLTA_SI02_01",
            },
        ],
    )
    monkeypatch.setattr(cr, "_batch_inventario_por_pon_keys", lambda _keys: {})

    payload = cr._cortes_rama_uncached(fecha="2026-06-09")
    assert payload["total_filtrado"] == 2
    principals = {i["principal"] for i in payload["items"]}
    assert "Tigre" in principals
    assert "San Isidro" in principals


def test_clasificar_impacto():
    from services.cortes_rama import _clasificar_impacto

    assert _clasificar_impacto(0) == "MODERADO"
    assert _clasificar_impacto(15) == "MODERADO"
    assert _clasificar_impacto(16) == "MODERADO"
    assert _clasificar_impacto(17) == "URGENTE"
    assert _clasificar_impacto(249) == "URGENTE"
    assert _clasificar_impacto(250) == "EMERGENCIA"


def test_parse_fecha_filtro():
    from datetime import date

    from services.cortes_rama import _parse_fecha_filtro

    assert _parse_fecha_filtro("") is None
    assert _parse_fecha_filtro("2026-06-01") == date(2026, 6, 1)
    assert _parse_fecha_filtro("hoy") is not None
    assert _parse_fecha_filtro("ayer") is not None


def test_filter_items_por_fecha_e_impacto():
    from services.cortes_rama import _filter_items

    items = [
        {
            "raised": "2026-06-09T15:00:00.000Z",
            "impacto": "URGENTE",
            "ont_total": 20,
            "ramas": ["A"],
            "vnos": {},
        },
        {
            "raised": "2026-06-08T15:00:00.000Z",
            "impacto": "EMERGENCIA",
            "ont_total": 300,
            "ramas": ["B"],
            "vnos": {},
        },
    ]
    from datetime import date

    out = _filter_items(items, fecha=date(2026, 6, 9))
    assert len(out) == 1
    assert out[0]["impacto"] == "URGENTE"
    out2 = _filter_items(items, impacto="EMERGENCIA")
    assert len(out2) == 1
    assert out2[0]["ont_total"] == 300


def test_detect_eventos_masivos():
    from services.cortes_rama import _detect_eventos_masivos

    items = [
        {
            "raised": "2026-06-09T15:00:00.000Z",
            "ont_total": 10,
            "pon_key": "A",
            "olt": "BA_OLTA_TG01_01",
            "causa": "LOSI_LOBI",
            "impacto": "MODERADO",
        },
        {
            "raised": "2026-06-09T15:00:30.000Z",
            "ont_total": 300,
            "pon_key": "B",
            "olt": "BA_OLTA_TG01_01",
            "causa": "LOSI_LOBI",
            "impacto": "EMERGENCIA",
        },
        {
            "raised": "2026-06-09T14:00:00.000Z",
            "ont_total": 5,
            "pon_key": "C",
            "olt": "BA_OLTA_SF01_01",
            "causa": "LOSI_LOBI",
            "impacto": "MODERADO",
        },
    ]
    eventos = _detect_eventos_masivos(items)
    assert len(eventos) == 1
    assert eventos[0]["cortes"] == 2
    assert eventos[0]["clientes"] == 310
    assert eventos[0]["impacto"] == "EMERGENCIA"
    assert eventos[0]["tipo"] == "fibra"
    assert eventos[0]["tipo_label"] == "Corte de fibra"
    assert eventos[0]["pon_keys"] == ["A", "B"]
    assert eventos[0]["pons"] == ["A", "B"]


def test_export_csv_evento_reporte_pon(monkeypatch):
    from services import cortes_rama as cr

    class FakeCur:
        def execute(self, sql, params):
            self.params = params

        def fetchall(self):
            return [
                (
                    "BA_OLTA_TG02_02-13-3-1",
                    "TG02-RATC-0-001047",
                    "CTO-A",
                    "1051234567",
                    1001,
                ),
                (
                    "BA_OLTA_TG02_02-13-3-2",
                    "TG02-RATC-0-001047",
                    "CTO-A",
                    "1051234568",
                    1001,
                ),
                (
                    "BA_OLTA_TG02_02-13-3-3",
                    "TG02-RATC-0-001047",
                    "CTO-B",
                    "1051234569",
                    3001,
                ),
            ]

    class FakeCtx:
        def __enter__(self):
            return FakeCur()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(cr, "db_cursor", lambda: FakeCtx())

    out = cr.export_csv_evento_reporte_pon(
        ["BA_OLTA_TG02_02-13-3"],
        principal="Tigre",
        ventana="2026-05-26 11:34",
    )
    assert out["ok"] is True
    csv = out["csv"]
    assert '"PON","RAMA","CTO","ACCESS ID","OPERADOR","ONT"' in csv
    assert '"PON 3","TG02-RATC-0-001047","CTO-A","1051234567","TASA"' in csv
    assert '","","","1051234568"' in csv
    assert '","","CTO-B","1051234569"' in csv
    assert '"BA_OLTA_TG02_02-13-3",' not in csv.split("RESUMEN:")[0]
    assert "RESUMEN:" in csv
    assert "PON: 1" in csv
    assert "RAMAS: 1" in csv
    assert "CTO: 2" in csv
    assert "ONT: 3" in csv
    assert "TASA: 2" in csv
    assert "DIRECTV: 1" in csv
    assert "# resumen" not in csv
    assert out["row_count"] == 3
    assert out["filename"].startswith("pones_seleccionados_")
    assert out["filename"].endswith(".csv")


def test_format_pon_export_flat_sparse_csv():
    from services.cortes_rama import _format_pon_export_flat_sparse_csv

    rows = [
        {"pon": "PON 3", "rama": "R1", "cto": "C1", "aid": "1", "operador": "TASA", "ont": "O1"},
        {"pon": "PON 3", "rama": "R1", "cto": "C1", "aid": "2", "operador": "TASA", "ont": "O2"},
        {"pon": "PON 3", "rama": "R1", "cto": "C2", "aid": "3", "operador": "TASA", "ont": "O3"},
    ]
    out = _format_pon_export_flat_sparse_csv(rows)
    assert out[1] == ["PON 3", "R1", "C1", "1", "TASA", "O1"]
    assert out[2] == ["", "", "", "2", "TASA", "O2"]
    assert out[3] == ["", "", "C2", "3", "TASA", "O3"]


def test_export_csv_evento_reporte_pon_sin_pon_400():
    from services.cortes_rama import export_csv_evento_reporte_pon

    out = export_csv_evento_reporte_pon([])
    assert out["ok"] is False
    assert out["status_code"] == 400


def test_dashboard_alarm_analyzer_evento_reporte_csv(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "export_csv_evento_reporte_pon",
        lambda keys, **kw: {
            "ok": True,
            "csv": "\ufeffPON\tRAMA\n",
            "filename": "reporte_test.csv",
        },
    )
    r = client.post(
        "/dashboard/alarm-analyzer/evento-reporte.csv",
        json={"pon_keys": ["BA_OLTA_TG02_02-13-3"], "principal": "Tigre"},
    )
    assert r.status_code == 200
    assert "attachment" in (r.headers.get("Content-Disposition") or "")
    assert "reporte_test.csv" in (r.headers.get("Content-Disposition") or "")


def test_detect_eventos_masivos_separa_fibra_y_luz():
    from services.cortes_rama import _detect_eventos_masivos

    items = [
        {
            "raised": "2026-06-09T15:00:00.000Z",
            "ont_total": 10,
            "pon_key": "A",
            "olt": "BA_OLTA_TG01_01",
            "principal": "Tigre",
            "causa": "LOSI_LOBI",
        },
        {
            "raised": "2026-06-09T15:00:30.000Z",
            "ont_total": 8,
            "pon_key": "B",
            "olt": "BA_OLTA_TG01_01",
            "principal": "Tigre",
            "causa": "LOSI_LOBI",
        },
        {
            "raised": "2026-06-09T15:01:00.000Z",
            "ont_total": 12,
            "pon_key": "C",
            "olt": "BA_OLTA_TG01_01",
            "principal": "Tigre",
            "causa": "DYING_GASP",
        },
        {
            "raised": "2026-06-09T15:01:30.000Z",
            "ont_total": 6,
            "pon_key": "D",
            "olt": "BA_OLTA_TG01_01",
            "principal": "Tigre",
            "causa": "DYING_GASP",
        },
    ]
    eventos = _detect_eventos_masivos(items)
    assert len(eventos) == 2
    assert {e["tipo"] for e in eventos} == {"fibra", "luz"}
    fibra = next(e for e in eventos if e["tipo"] == "fibra")
    luz = next(e for e in eventos if e["tipo"] == "luz")
    assert fibra["cortes"] == 2 and fibra["clientes"] == 18
    assert luz["cortes"] == 2 and luz["clientes"] == 18


def test_detect_eventos_masivos_suma_varias_olt_mismo_sitio():
    """Tigre: varias OLT en la misma ventana → un solo evento con clientes sumados."""
    from services.cortes_rama import _detect_eventos_masivos

    base = {
        "raised": "2026-05-26T14:34:00.000Z",
        "principal": "Tigre",
        "causa": "LOSI_LOBI",
    }
    items = [
        {**base, "ont_total": 144, "pon_key": "A", "olt": "BA_OLTA_TG01_01"},
        {**base, "ont_total": 144, "pon_key": "B", "olt": "BA_OLTA_TG01_01"},
        {**base, "ont_total": 31, "pon_key": "C", "olt": "BA_OLTA_TG02_02"},
        {**base, "ont_total": 31, "pon_key": "D", "olt": "BA_OLTA_TG02_02"},
    ]
    eventos = _detect_eventos_masivos(items)
    assert len(eventos) == 1
    assert eventos[0]["principal"] == "Tigre"
    assert eventos[0]["cortes"] == 4
    assert eventos[0]["clientes"] == 350
    assert eventos[0]["impacto"] == "EMERGENCIA"
    assert len(eventos[0]["olts"]) == 2


def test_aplicar_impacto_cortes_simultaneos_suma_clientes():
    """Escobar: 9 + 11 clientes en ventana 08:34–08:35 → urgente."""
    from services.cortes_rama import _aplicar_impacto_cortes_simultaneos, _enrich_item_impacto

    items = [
        _enrich_item_impacto(
            {
                "raised": "2026-06-10T11:35:00.000Z",
                "olt": "BA_OLTA_ES01_01",
                "principal": "Escobar",
                "causa": "LOSI_LOBI",
                "ont_total": 9,
                "pon_key": "BA_OLTA_ES01_01-7-3",
            }
        ),
        _enrich_item_impacto(
            {
                "raised": "2026-06-10T11:34:00.000Z",
                "olt": "BA_OLTA_ES01_01",
                "principal": "Escobar",
                "causa": "LOSI_LOBI",
                "ont_total": 11,
                "pon_key": "BA_OLTA_ES01_01-9-2",
            }
        ),
    ]
    out = _aplicar_impacto_cortes_simultaneos(items)
    assert all(r["evento_simultaneo"] for r in out)
    assert out[0]["impacto_pon"] == "MODERADO"
    assert out[1]["impacto_pon"] == "MODERADO"
    assert out[0]["impacto"] == "URGENTE"
    assert out[1]["impacto"] == "URGENTE"
    assert out[0]["evento_clientes"] == 20
    assert out[0]["evento_cortes"] == 2


def test_sort_cortes_items():
    from services.cortes_rama import _sort_cortes_items

    items = [
        {"pon_key": "A", "raised": "2026-06-09T08:00:00.000Z", "ont_total": 5},
        {"pon_key": "B", "raised": "2026-06-09T12:00:00.000Z", "ont_total": 2},
        {"pon_key": "C", "raised": "2026-06-09T10:00:00.000Z", "ont_total": 20},
    ]
    reciente = [r["pon_key"] for r in _sort_cortes_items(items, "reciente")]
    assert reciente == ["B", "C", "A"]
    antiguo = [r["pon_key"] for r in _sort_cortes_items(items, "antiguo")]
    assert antiguo == ["A", "C", "B"]
    clientes = [r["pon_key"] for r in _sort_cortes_items(items, "clientes")]
    assert clientes == ["C", "A", "B"]


def test_filter_items_por_vno():
    from services.cortes_rama import _filter_items

    items = [
        {"vnos": {"TASA": 5}, "ramas": ["A"]},
        {"vnos": {"DIRECTV": 2}, "ramas": ["B"]},
    ]
    out = _filter_items(items, vno="TASA")
    assert len(out) == 1
    assert out[0]["ramas"] == ["A"]


def test_dashboard_alarm_analyzer_get_renders(client):
    r = client.get("/dashboard/alarm-analyzer")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Alarm Analyzer" in html
    assert "Cortes de Rama" not in html
    assert 'id="cortes-table"' in html
    assert "Clientes afectados" in html
    assert "cortes-vno-resumen" in html
    assert 'class="cortes-view-row"' in html
    assert "Ordenar" in html
    assert "Por sitio / LT" not in html
    assert "Solo con RAMA" not in html
    assert "Solo nuevos" not in html
    assert 'id="cortes-sort"' in html
    assert 'id="cortes-fecha-dia"' in html
    assert "flatpickr" in html
    assert "estadisticas-flatpickr.css" in html
    assert "noc-estadisticas-flatpickr.js" in html
    assert "calidad-estadisticas-fecha-wrap" in html
    assert 'placeholder="Hoy"' in html
    assert 'id="cortes-fecha-preset"' not in html
    assert 'id="cortes-estado"' in html
    assert "Activas + Cleared" not in html
    assert 'value="todas"' not in html
    assert "eventos masivos" in html.lower()
    assert 'id="cortes-refresh"' in html
    assert "Auto-refresh" in html
    assert "15 segundos" in html
    assert '<option value="ayer">' not in html
    assert "dashboard-cortes-rama.js" in html
    assert "dashboard-cortes-rama.css" in html
    js = open("static/js/dashboard-cortes-rama.js", encoding="utf-8").read()
    assert "_setCortesFechaHoy" in js
    assert "noc-fp-footer-btn" in js
    assert "Todas las fechas" in js
    assert "cortesRamaSeenPonKeysV1" in js
    assert "_buildDisplayBlocks" in js
    assert "_renderEventoTableGroupRow" in js
    assert "_formatVentanaArt" in js
    assert "_isEventoBlockExpanded" in js
    assert "initCortesRamaDashboard" in js
    assert "bootCortesRamaDashboard" in js
    assert "window.fetchCortes = fetchCortes" in js
    assert "_readCortesRamaState" in js
    assert "cortes-estado" in js
    assert "_initCortesFechaPicker" in js
    assert "NocEstadisticasFlatpickr" in js
    assert "/api/alarm-analyzer" in js
    assert "cortes-evento-reporte-btn" in js
    assert "cortes-evento-olt-btn" in js
    assert "_buildOltUrlFromPonKeys" in js
    assert "_renderIdListCell" in js
    assert "_renderRamasCell" in js
    assert "cortes-cto-count" in js
    assert "select_pon=" in js
    assert "cortes-tbody" in js
    assert "data-pon-key" in js
    assert "_onCortesReporteButtonClick" in js
    assert "exportEventoReporte" in js
    assert "_stateStore.load" not in js
    assert "cortes-fecha-preset" not in js


def test_api_cortes_rama_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_cortes_rama",
        lambda **_kw: {
            "ok": True,
            "items": [
                {
                    "causa": "LOSI_LOBI",
                    "olt": "BA_OLTA_TG02_02",
                    "pon_key": "BA_OLTA_TG02_02-13-3",
                    "ramas": ["TG02-RATC-0-001047"],
                    "ont_total": 5,
                    "vno_list": [{"vno": "TASA", "count": 5}],
                }
            ],
            "totales": {
                "TOTAL": 1,
                "LOSI_LOBI": 1,
                "DYING_GASP": 0,
                "CLIENTES_AFECTADOS": 5,
            },
            "vno_resumen": [{"vno": "TASA", "count": 5}],
            "principals": ["TG"],
            "vnos": ["TASA"],
        },
    )
    r = client.get("/api/alarm-analyzer")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["items"][0]["ont_total"] == 5


def test_api_alarm_analyzer_legacy_redirect(client):
    r = client.get("/api/cortes-rama", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["Location"].endswith("/api/alarm-analyzer")


def test_export_cortes_rama_csv(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "export_csv_cortes_rama",
        lambda **_kw: {
            "ok": True,
            "csv": "CAUSA,OLT\nLOSi,BA_OLTA_X\n",
        },
    )
    r = client.get("/dashboard/alarm-analyzer/export.csv")
    assert r.status_code == 200
    assert "LOSi" in r.get_data(as_text=True)
    assert "attachment" in (r.headers.get("Content-Disposition") or "")
    assert "alarm_analyzer.csv" in (r.headers.get("Content-Disposition") or "")


def test_cortes_rama_inventario_query_exists():
    from queries import QUERIES

    sql = QUERIES["cortes_rama_inventario_por_pon"]
    assert "invocator_system" in sql
    assert "LIKE ANY(%s)" in sql


def test_dashboard_entry_redirect_alarm_analyzer(client):
    r = client.get("/dashboard?tab=alarm-analyzer", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/dashboard/alarm-analyzer")


def test_dashboard_cortes_rama_legacy_redirect(client):
    r = client.get("/dashboard/cortes-rama", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["Location"].endswith("/dashboard/alarm-analyzer")
