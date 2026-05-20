def test_index_access_id_sin_fila_estado_solo_tx_rx(client, monkeypatch):
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
    assert "<th>TX (dBm)</th><td id=\"s0-tx\"" in html
    assert "<th>RX (dBm)</th><td id=\"s0-rx\"" in html
    assert "<th>Alarmas</th><td id=\"s0-alarmas\"" in html
    assert "estado-id" not in html
    assert "(aux.bajada_inventario)" in html


def test_index_alphanumeric_access_id_resolves(client, monkeypatch):
    """Access ID alfanumérico (p. ej. VNO ATC) debe resolverse en Consulta, no solo dígitos."""
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_access_id_detalle_desde_bajada_inventario",
        lambda aid: (
            {
                "AID": aid,
                "OPERADOR": "ATC",
                "Status": "IN SERVICE",
                "CTO": "SF01-FATC-8-100001",
                "RAMA": "SF01-RATC-0-000100",
                "ONT": "BA_OLTA_SF01_01-1-1-1",
                "SN": "SN1",
                "TX": None,
                "RX": None,
                "fuente_detalle": "bajada_inventario",
            }
            if aid == "fes_a5_23"
            else None
        ),
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "fes_a5_23"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "fes_a5_23" in html
    assert "SF01-FATC-8-100001" in html


def test_index_cto_table_sin_columna_estado(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_cto_estructura",
        lambda _cto: [
            {
                "AID": "105",
                "OPERADOR": "TASA",
                "RAMA": "TG01-RATC-0-000308",
                "PRINCIPAL": "Tigre",
                "ONT": "BA_OLTA_TG01_02-2-15-8",
                "SN": "04EDFBADD5F81",
                "STATUS": "IN SERVICE",
                "TX": None,
                "RX": None,
            }
        ],
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "TG01-FATC-8-100987"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<th>Status</th>" in html and "<th>TX (dBm)</th>" in html and "<th>RX (dBm)</th>" in html
    assert "<th>Estado</th>" not in html
    assert "id=\"s0-tx-105\"" in html
    assert "id=\"s0-st-105\"" not in html


def test_index_rama_table_sin_columna_estado(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_rama_estructura",
        lambda _rama: {
            "TG01-FATC-8-100987": [
                {
                    "AID": "105",
                    "OPERADOR": "TASA",
                    "PRINCIPAL": "Tigre",
                    "ONT": "BA_OLTA_TG01_02-2-15-8",
                    "SN": "04EDFBADD5F81",
                    "STATUS": "IN SERVICE",
                    "TX": None,
                    "RX": None,
                }
            ]
        },
    )

    r = client.post("/", data={"value": "TG01-RATC-0-000308"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<th>AID</th>" in html and "<th>TX</th>" in html and "<th>RX</th>" in html
    assert "<th>ESTADO</th>" not in html
    assert "id=\"s0-tx-105\"" in html
    assert "consulta-cto-block" in html
    assert "consulta-cto-head-row--subrama" in html
    assert "Consultar RX" in html
