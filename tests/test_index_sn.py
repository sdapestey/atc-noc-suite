def test_index_access_id_renders_sn_field(client, monkeypatch):
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
    assert "<th>SN</th>" in html
    assert "04EDFBADD5F81" in html


def test_index_cto_table_omits_sn_column(client, monkeypatch):
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
    assert "<h2>CTO</h2>" in html
    start = html.index("<h2>CTO</h2>")
    bloque = html[start : start + 4500]
    assert "<th>SN</th>" not in bloque
    assert "04EDFBADD5F81" not in bloque


def test_index_rama_table_has_sitio_status_without_sn(client, monkeypatch):
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
    assert "<th>AID</th>" in html and "<th>STATUS</th>" in html and "<th>SITIO</th>" in html
    assert "<th>SN</th>" not in html
    assert "04EDFBADD5F81" not in html
    assert "Tigre" in html
    assert "IN SERVICE" in html
    assert "data-consulta-rama-search-map" in html
    assert 'aria-label="Mapa — CTO en esta RAMA"' in html
    assert "TG01-RATC-0-000308" in html
    assert "data-consulta-cto-map" in html
    assert "Ver historico" in html
    assert "/dashboard/potencias-historico?ratc=TG01-RATC-0-000308" in html
