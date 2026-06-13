def test_dashboard_altiplano_get_login_page_sin_sesion(client):
    r = client.get("/dashboard/altiplano")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="orquestador-login-form"' in html
    assert "Acceso Altiplano" in html
    assert "orquestador-login-card" in html
    assert "orquestador-login-input" in html
    assert 'id="login_username"' in html
    assert 'id="login_password"' in html
    assert "orquestador-login-submit" in html
    assert "orquestador-login-note" in html
    assert "orquestador-credit" in html
    assert "Desarrollo e implementación por Lucas Gimenez" in html


def test_dashboard_altiplano_get_panel_cuando_hay_sesion(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_user"] = "tester_inp"
        sess["orquestador_inp_token"] = "dummy-token"

    r = client.get("/dashboard/altiplano")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Crear ONT Connection" in html
    assert "ont-connection" in html
    assert 'id="alt-tab-inp"' in html
    assert 'id="alt-tab-vno"' in html
    assert 'id="alt-inp-tab-creacion"' in html
    assert 'id="alt-inp-tab-borrado"' in html
    assert 'id="alt-inp-tab-consulta"' in html
    assert 'id="btn-consulta-run"' in html
    assert 'id="consulta_query"' in html
    assert "suite-search-surface" in html
    assert "noc-suite-surface.css" in html
    assert "consultaClassifyQuery" in html
    assert "Location Name#Slice Owner Name#PON Type" in html
    assert "Required Network State" in html
    assert "Alignment State" in html
    assert "data-consulta-act=" in html
    assert '"sync"' in html and "consultaRowActionsCell" in html
    assert 'id="consulta-rn-dialog"' in html
    assert 'id="consulta-tasa-hsi-dialog"' in html
    assert 'id="consulta-success-toast"' in html
    assert "consultaToast" in html
    assert "consultaRowTasaHsiEditAllowed" in html
    assert 'act === "tasa-hsi"' in html
    assert "Traffic Descriptor Profile" in html
    assert "/dashboard/altiplano/actualizar-tasa-composite-profiles" in html
    assert "/dashboard/altiplano/tasa-composite-profile-suggestions" in html
    assert "consultaFetchTasaHsiSuggestions" in html
    assert "consulta-tasa-hsi-upstream-suggest" in html
    assert "altiplano-tasa-hsi-dialog" in html
    assert "consultaRowRnEditAllowed" in html
    assert "consultaRnTargetOptions" in html
    assert 'act === "rn"' in html
    assert "consultaRunActivateAndSync" in html
    assert "consultaRunFixItChain" in html
    assert "consultaShouldShowMultiSelect" in html
    assert "consulta-advanced-details" in html
    assert "btn-consulta-advanced-run" in html
    assert "consulta_advanced_device" in html
    assert "consultaGetAdvancedFilters" in html
    assert "consultaAdvancedActiveAlignedBlocked" in html
    assert "CONSULTA_BLOCKED_ACTIVE_ALIGNED_MSG" in html
    assert "runConsultaAdvanced" in html
    assert "consulta-bulk-bar" in html
    assert "Sincronizar seleccionados" in html
    assert "Corregir dependencias" in html
    assert "consultaRunBulkFix" in html
    assert "btn-consulta-bulk-fix" in html
    assert "Eliminar seleccionados" in html
    assert 'kind === "fix"' in html
    assert 'act === "fix"' in html
    assert "Corregir dependencias L1" in html
    assert "altiplano-result-dialog" in html
    assert "altiplanoResultDialog" in html
    assert "altiplanoInpErrorDialog" in html
    assert 'id="altiplano-result-detail"' in html
    assert "consultaSetFixItBusy" in html
    assert "Fix it?" not in html
    assert "Activar (Active) y sincronizar (Aligned)" in html
    assert "/dashboard/altiplano/corregir-dependencias-l1" in html
    assert "create-l1" in html
    assert "/dashboard/altiplano/crear-ont-connection-faltante" in html
    assert "btn-consulta-create-from-search" in html
    assert "applyInpCreatePrefill" in html
    assert "consultaRowActionsCell" in html
    assert "/dashboard/altiplano/sincronizar-intent" in html
    assert "/dashboard/altiplano/actualizar-required-network-state" in html
    assert html.index('id="alt-inp-tab-consulta"') < html.index('id="alt-inp-tab-creacion"')
    assert html.index('id="alt-inp-tab-creacion"') < html.index('id="alt-inp-tab-borrado"')
    assert "dash-segment" in html
    assert 'aria-label="Operaciones INP"' in html
    assert "borrar-intent" in html or 'id="btn-borrado-run"' in html
    assert "borrar-intent-lote" in html
    assert 'id="borrado-lote-dropzone"' in html
    assert 'id="alt-vno-tab-tasa"' in html
    assert 'id="alt-vno-tab-directv"' in html
    assert 'id="alt-vno-tab-iplan"' in html
    assert 'id="alt-vno-tab-metrotel"' in html
    assert 'id="alt-vno-tab-sion"' in html
    assert 'id="alt-vno-tab-cambio-cto"' not in html
    assert 'id="alt-vno-ftth-cto-section"' in html
    assert 'id="ftth-cto-form"' in html
    assert "Cambio de CTO" in html
    assert "Web ToolBox FTTH Norte" in html
    assert 'id="ftth-cto-id"' in html
    assert 'id="ftth-cto-access-id"' in html
    assert 'id="ftth-cto-ally-id"' in html
    assert 'for="ftth-cto-aliado"' not in html
    assert "consulta-search-card" in html
    assert "consulta-field" in html
    assert 'class="search-icon"' in html
    assert "altiplano-consulta-shell" in html
    assert "/dashboard/altiplano/vno/cambiar-cto" in html
    assert 'id="tasa-postman-api"' in html
    assert "Configure / Create ONT + Services" in html
    assert "Colección Postman" in html or "TASA - PROD ALTIPLANO" in html
    assert "Orquestador NOC ATC" in html
    assert 'id="tasa-console-out"' in html
    assert 'id="tasa-btn-ejecutar"' in html
    assert "altiplano-inp-vno-offer" in html
    assert "btn-inp-goto-vno" in html
    assert 'id="device_location_full"' in html
    assert "parseFullOltDeviceName" in html
    assert 'id="sitio"' in html
    assert '<optgroup label="Moreno">' in html
    assert '<option value="MR01_01">MR01_01</option>' in html
    assert '<option value="VL01_03">VL01_03</option>' in html
    assert "Operador" not in html
    assert "Entorno NBI" not in html
    assert 'id="lt" type="text" autocomplete="off"' in html
    assert 'id="pon" type="text" autocomplete="off"' in html
    assert 'id="vno"' in html
    assert '<option value="1001">1001 - TASA</option>' in html
    assert '<option value="3001">3001 - DIRECTV</option>' in html
    assert '<option value="2806">2806 - ATC</option>' in html
    assert "for=\"pir\"" not in html
    assert "for=\"cir\"" not in html
    assert "tester_inp" in html
    assert 'id="btn-orquestador-logout"' in html
    assert "orquestador-credit" in html
    assert "Desarrollo e implementación por Lucas Gimenez" in html


def test_dashboard_altiplano_login_ok(client, monkeypatch):
    import time

    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: "fresh-token")

    r = client.post(
        "/dashboard/altiplano/login",
        json={"username": "u_inp", "password": "secret"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True

    with client.session_transaction() as sess:
        assert sess.get("orquestador_ok") is True
        assert sess.get("orquestador_user") == "u_inp"
        assert sess.get("orquestador_inp_token") == "fresh-token"
        assert float(sess.get("orquestador_expires_at") or 0) > time.time()


def test_dashboard_altiplano_sesion_caducada_muestra_login(client):
    import time

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_user"] = "u_inp"
        sess["orquestador_inp_token"] = "expired-token"
        sess["orquestador_expires_at"] = time.time() - 60

    r = client.get("/dashboard/altiplano")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'id="orquestador-login-form"' in html
    assert "expired-token" not in html

    with client.session_transaction() as sess:
        assert "orquestador_ok" not in sess
        assert "orquestador_inp_token" not in sess


def test_dashboard_altiplano_login_fallo_altiplano(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: None)

    r = client.post(
        "/dashboard/altiplano/login",
        json={"username": "bad", "password": "bad"},
    )
    assert r.status_code == 401
    payload = r.get_json()
    assert payload["ok"] is False


def test_dashboard_altiplano_logout_limpia_sesion(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_user"] = "x"
        sess["orquestador_inp_token"] = "t"

    r = client.post("/dashboard/altiplano/logout")
    assert r.status_code == 200
    with client.session_transaction() as sess:
        assert "orquestador_ok" not in sess
        assert "orquestador_inp_token" not in sess


def test_dashboard_altiplano_ont_connection_missing_field_400(client):
    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "sitio": "VL01_01",
            "device_name": "BA_OLTA_VL01_01",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "fiber_name": "FIBRA-1",
            # access_id faltante
        },
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "access_id" in payload["message"]


def test_dashboard_altiplano_ont_connection_missing_sitio_400(client):
    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "access_id": "1051234567",
        },
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "sitio" in payload["message"]


def test_dashboard_altiplano_ont_connection_sin_sesion_ni_body_401(client):
    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "sitio": "VL01_01",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "access_id": "1051234567",
        },
    )
    assert r.status_code == 401


def test_dashboard_altiplano_ont_connection_success_201(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "message": "ONT Connection creada correctamente",
            "target": "BA_OLTA_VL01_01-1-1-66#1001#gpon",
        }

    monkeypatch.setattr(
        routes,
        "crear_ont_connection_intent",
        fake_create,
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_user"] = "sess_u"
        sess["orquestador_inp_token"] = "sess-test-token"

    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "sitio": "VL01_01",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "access_id": "1051234567",
            "pir": 9999,
            "cir": 9999,
        },
    )
    assert r.status_code == 201
    payload = r.get_json()
    assert payload["ok"] is True
    assert "target" in payload
    assert captured["entorno_nbi"] == "INP"
    assert captured["device_name"] == "BA_OLTA_VL01_01"
    assert captured["fiber_name"] == "BA_OLTA_VL01_01-1-1"
    assert captured["pir"] == 1000
    assert captured["cir"] == 35
    assert captured["nbi_bearer_token"] == "sess-test-token"


def test_dashboard_altiplano_ont_connection_success_con_credenciales_body(client, monkeypatch):
    """Compatibilidad: sin sesión pero con usuario/contraseña en el JSON (scripts/tests)."""
    import web.routes as routes

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "message": "ONT Connection creada correctamente",
            "target": "x",
        }

    monkeypatch.setattr(routes, "crear_ont_connection_intent", fake_create)

    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "sitio": "VL01_01",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "access_id": "1051234567",
            "altiplano_user": "user_ui_test",
            "altiplano_password": "pass_ui_test",
        },
    )
    assert r.status_code == 201
    assert captured["nbi_username"] == "user_ui_test"
    assert captured["nbi_password"] == "pass_ui_test"


def test_dashboard_altiplano_consultar_intent_parametros_vacios_400(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post("/dashboard/altiplano/consultar-intent", json={})
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "matches" in payload
    assert "búsqueda avanzada" in payload["message"].lower()


def test_dashboard_altiplano_consultar_intent_solo_filtros_avanzados_200(client, monkeypatch):
    import web.routes as routes

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    def fake_buscar(token, **kw):
        assert kw.get("filter_alignment_state") == ["misaligned"]
        return {
            "ok": True,
            "message": "1 intent",
            "matches": [
                {
                    "target": "BA_OLTA_T#1001#gpon",
                    "access_id": "x",
                    "network_state": "Active",
                    "alignment_state": "Misaligned",
                }
            ],
            "search_source": "gui-search-intents-advanced",
        }

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={
            "advanced_filters": {
                "required_network_state": [],
                "alignment_state": ["misaligned"],
            }
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert len(payload["matches"]) == 1


def test_dashboard_altiplano_consultar_intent_active_aligned_blocked_400(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={
            "advanced_filters": {
                "required_network_state": ["active"],
                "alignment_state": ["aligned"],
            }
        },
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "Active + Aligned" in payload["message"]


def test_dashboard_altiplano_consultar_intent_advanced_no_match_keeps_message(client, monkeypatch):
    import web.routes as routes

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    msg = "Sin intents ont-connection para los filtros indicados."

    def fake_buscar(token, **kw):
        return {
            "ok": True,
            "message": msg,
            "matches": [],
            "no_match": True,
            "search_source": "gui-search-intents-advanced",
        }

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={
            "advanced_filters": {
                "required_network_state": ["active"],
                "alignment_state": ["misaligned"],
            }
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["message"] == msg
    assert "Device Name" not in payload["message"]


def test_dashboard_altiplano_consultar_intent_id_invalido_400(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "", "by_id": "no-es-num-ni-uuid@"},
    )
    assert r.status_code == 400


def test_dashboard_altiplano_consultar_intent_rechaza_uuid_400(client):
    """La consulta INP no admite UUID de intent (solo Access ID o device/target)."""
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "", "by_id": "550e8400-e29b-41d4-a716-446655440000"},
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "uuid" in (payload.get("message") or "").lower()


def test_dashboard_altiplano_consultar_intent_access_id_alfanumerico_200(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "resolver_target_ont_connection_por_access_id",
        lambda _aid: {
            "ok": True,
            "device_name_for_query": "BA_OLTA_ES01_01-1-1-99#1001#gpon",
            "device_location_prefix": "BA_OLTA_ES01_01-1-1-99",
            "suggested_target": "BA_OLTA_ES01_01-1-1-99#1001#gpon",
        },
    )

    def fake_buscar(token, **kwargs):
        assert kwargs.get("access_id") == "ALCL00010199"
        assert kwargs.get("access_id_match_mode") == "prefix"
        assert kwargs.get("device_prefix") is None
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok-consulta-aid-alpha"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "", "by_id": "ALCL00010199"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True


def test_dashboard_altiplano_consultar_intent_access_id_numerico_exact_match_mode(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "resolver_target_ont_connection_por_access_id",
        lambda _aid: {"ok": True, "device_name_for_query": "BA_OLTA_X#1001#gpon"},
    )

    def fake_buscar(token, **kwargs):
        assert kwargs.get("access_id") == "127240110"
        assert kwargs.get("access_id_match_mode") == "exact"
        assert kwargs.get("device_prefix") is None
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "", "by_id": "127240110"},
    )
    assert r.status_code == 200


def test_dashboard_altiplano_consultar_intent_access_id_sufijo_numerico_usa_inventario_nbi(
    client, monkeypatch
):
    """Tokens tipo BORRAR_003: modo exacto; NBI amplio por Access ID (varios targets como la GUI)."""
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "resolver_target_ont_connection_por_access_id",
        lambda _aid: {
            "ok": True,
            "device_name_for_query": "BA_OLTA_SF01_02-15-4-17#3001#gpon",
            "device_location_prefix": "BA_OLTA_SF01_02-15-4-17",
            "suggested_target": "BA_OLTA_SF01_02-15-4-17#3001#gpon",
        },
    )

    captured = {}

    def fake_buscar(token, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok-borrar003"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "", "by_id": "BORRAR_003"},
    )
    assert r.status_code == 200
    assert captured.get("access_id") == "BORRAR_003"
    assert captured.get("access_id_match_mode") == "exact"
    assert captured.get("device_prefix") is None


def test_dashboard_altiplano_consultar_intent_sin_sesion_401(client):
    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "BA_OLTA_X"},
    )
    assert r.status_code == 401


def test_dashboard_altiplano_consultar_intent_target_solo_en_by_id_200(client, monkeypatch):
    """Si el target completo llega solo en ``by_id`` (API / copiar-pegar), debe consultarse por device_prefix."""
    import web.routes as routes

    captured = {}

    def fake_buscar(token, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok-consulta-by-target"

    tgt = "BA_OLTA_ES01_01-12-14-15#3001#gpon"
    r = client.post("/dashboard/altiplano/consultar-intent", json={"by_id": tgt})
    assert r.status_code == 200
    assert captured.get("device_prefix") == tgt
    assert captured.get("access_id") is None


def test_dashboard_altiplano_consultar_intent_descarta_by_id_invalido_si_hay_target_hash(
    client, monkeypatch
):
    import web.routes as routes

    captured = {}

    def fake_buscar(token, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    tgt = "BA_OLTA_ES01_01-12-14-15#3001#gpon"
    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": tgt, "by_id": "129322928\u200b"},
    )
    assert r.status_code == 200
    assert captured.get("device_prefix") == tgt
    assert captured.get("access_id") is None


def test_dashboard_altiplano_consultar_intent_ok_200(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_buscar(token, **kwargs):
        captured["token"] = token
        captured.update(kwargs)
        return {
            "ok": True,
            "message": "1 intent(s) encontrado(s)",
            "matches": [
                {
                    "target": "BA_OLTA_ES01_01-1-1-99#3001#gpon",
                    "location_slice_pon": "BA_OLTA_ES01_01-1-1-99#3001#gpon",
                    "access_id": "1051234567",
                    "intent_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "intent_type": "ont-connection",
                    "required_network_state": "active",
                    "network_state": "Active",
                    "alignment_state": "Aligned",
                }
            ],
        }

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "sess-token-consulta"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "BA_OLTA_ES01_01-1-1-99", "by_id": ""},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["access_id"] == "1051234567"
    assert payload["matches"][0]["location_slice_pon"] == "BA_OLTA_ES01_01-1-1-99#3001#gpon"
    assert payload["matches"][0]["network_state"] == "Active"
    assert payload["matches"][0]["alignment_state"] == "Aligned"
    assert captured["token"] == "sess-token-consulta"
    assert captured["device_prefix"] == "BA_OLTA_ES01_01-1-1-99"


def test_dashboard_altiplano_consultar_intent_access_id_sin_match_suggest_create(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "resolver_target_ont_connection_por_access_id",
        lambda _aid: {
            "ok": True,
            "device_location_prefix": "BA_OLTA_ES01_01-9-4-11",
            "suggested_target": "BA_OLTA_ES01_01-9-4-11#1001#gpon",
            "invocator_system": 1001,
        },
    )
    monkeypatch.setattr(
        routes,
        "buscar_intents_ont_connection_inp",
        lambda *_a, **_kw: {
            "ok": True,
            "message": "No existe ese Access ID en Altiplano",
            "matches": [],
            "no_match": True,
            "suggest_create": True,
            "consulta_criterion": "access_id",
        },
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post("/dashboard/altiplano/consultar-intent", json={"by_id": "999888777"})
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["message"] == "No existe ese Access ID en Altiplano"
    assert payload.get("suggest_create") is True
    assert payload["create_prefill"]["access_id"] == "999888777"
    assert payload["create_prefill"]["sitio"] == "ES01_01"


def test_dashboard_altiplano_consultar_intent_solo_access_id_resolver_falla_sigue_nbi(
    client, monkeypatch
):
    """Si ATC no tiene el AID, no fallar: consultar Altiplano por access_id (listado NBI)."""
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "resolver_target_ont_connection_por_access_id",
        lambda _aid: {"ok": False, "message": "Access ID no encontrado en inventario ATC."},
    )
    captured = {}

    def fake_buscar(token, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "message": "1 intent encontrado",
            "matches": [
                {
                    "target": "BA_OLTA_X#1001#gpon",
                    "access_id": "1050000001",
                }
            ],
        }

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"by_id": "1050000001"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload.get("inventory_miss_fallback") is True
    assert len(payload["matches"]) == 1
    assert captured.get("access_id") == "1050000001"
    assert captured.get("device_prefix") is None


def test_dashboard_altiplano_consultar_intent_access_id_enriquece_operador(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "resolver_target_ont_connection_por_access_id",
        lambda _aid: {
            "ok": True,
            "device_location_prefix": "BA_OLTA_ES01_01-1-1-1",
            "suggested_target": "BA_OLTA_ES01_01-1-1-1#1001#gpon",
            "invocator_system": 1001,
        },
    )
    monkeypatch.setattr(
        routes,
        "buscar_intents_ont_connection_inp",
        lambda *_a, **_kw: {
            "ok": True,
            "message": "1 intent encontrado",
            "matches": [
                {
                    "target": "BA_OLTA_ES01_01-1-1-1#1001#gpon",
                    "location_slice_pon": "BA_OLTA_ES01_01-1-1-1#1001#gpon",
                    "access_id": "1055568367",
                }
            ],
        },
    )

    def fake_enriquecer(out, **kwargs):
        out = dict(out)
        out["consulta_layout"] = "access_id_tabs"
        out["operator_resolution"] = {
            "operator": "TASA",
            "found": True,
            "operator_device_name": "BA_OLT_E501_01-1-1-1#1001#gpon",
        }
        out["matches"][0]["inp_device_name"] = "BA_OLTA_ES01_01-1-1-1"
        out["vno_matches"] = [
            {
                "target": "BA_OLT_E501_01-1-1-1#1001#gpon",
                "location_slice_pon": "BA_OLT_E501_01-1-1-1#1001#gpon",
                "access_id": "1055568367",
            }
        ]
        return out

    monkeypatch.setattr(routes, "enriquecer_consulta_con_operador", fake_enriquecer)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"by_id": "1055568367"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["consulta_layout"] == "access_id_tabs"
    assert payload["matches"][0]["inp_device_name"] == "BA_OLTA_ES01_01-1-1-1"
    assert len(payload["vno_matches"]) == 1
    assert payload["operator_resolution"]["operator"] == "TASA"


def test_dashboard_altiplano_consultar_intent_solo_access_id_resuelve_inventario(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "resolver_target_ont_connection_por_access_id",
        lambda _aid: {
            "ok": True,
            "device_name_for_query": "BA_OLTA_Z-1-1-1#1001#gpon",
            "device_location_prefix": "BA_OLTA_Z-1-1-1",
            "suggested_target": "BA_OLTA_Z-1-1-1#1001#gpon",
            "invocator_system": 1001,
        },
    )

    captured = {}

    def fake_buscar(token, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"by_id": "1052755742"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["inventory_resolution"]["device_location_prefix"] == "BA_OLTA_Z-1-1-1"
    assert captured["device_prefix"] is None
    assert captured["access_id"] == "1052755742"
    assert captured.get("access_id_match_mode") == "exact"


def test_dashboard_altiplano_consultar_intent_upstream_502(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "buscar_intents_ont_connection_inp",
        lambda *_a, **_k: {"ok": False, "message": "Sin datos", "matches": []},
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "BA_OLTA_X"},
    )
    assert r.status_code == 502


def test_dashboard_altiplano_consultar_intent_rechaza_device_y_access_juntos_400(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "BA_OLTA_X-1-1-1", "by_id": "1050000001"},
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "ambos" in (payload.get("message") or "").lower()


def test_dashboard_altiplano_consultar_intent_device_sin_ba_olta_400(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "OTHER_OLTA_01-1-1-1", "by_id": ""},
    )
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_dashboard_altiplano_consultar_intent_target_head_sin_ba_olta_400(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "FOO#3001#gpon", "by_id": ""},
    )
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_dashboard_altiplano_consultar_intent_campo_query_unico_200(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_buscar(token, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok-query"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"query": "1051999888"},
    )
    assert r.status_code == 200
    assert captured.get("access_id") == "1051999888"
    assert captured.get("device_prefix") is None


def test_dashboard_altiplano_consultar_intent_by_id_prefijo_ba_olta_remapea_a_device(
    client, monkeypatch
):
    import web.routes as routes

    captured = {}

    def fake_buscar(token, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "buscar_intents_ont_connection_inp", fake_buscar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/consultar-intent",
        json={"device_name": "", "by_id": "BA_OLTA_ES01_01-9-9-9"},
    )
    assert r.status_code == 200
    assert captured.get("device_prefix") == "BA_OLTA_ES01_01-9-9-9"
    assert captured.get("access_id") is None


def test_dashboard_altiplano_ont_connection_upstream_fail_502(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "crear_ont_connection_intent",
        lambda **_kwargs: {
            "ok": False,
            "message": "No se pudo autenticar contra Altiplano",
        },
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "IPLAN",
            "sitio": "TG01_01",
            "lt": "2",
            "pon": "5",
            "ont": "12",
            "vno": "1001",
            "access_id": "1050000012",
        },
    )
    assert r.status_code == 502
    payload = r.get_json()
    assert payload["ok"] is False


def test_dashboard_altiplano_borrar_intent_ok_200(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "borrar_inp_con_cascada_vno",
        lambda token, device_name, by_id, **kw: {
            "ok": True,
            "message": "Borrado en cascada completado: Delete Services → Delete ONT → ONT Connection (INP).",
            "target": "BA_OLTA_Z#1001#gpon",
            "access_id": "1051111222",
            "vno_steps": [{"label": "Delete ONT", "ok": True}],
            "cascade": True,
        },
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "sess-del"

    r = client.post(
        "/dashboard/altiplano/borrar-intent",
        json={"device_name": "BA_OLTA_Z#1001#gpon"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert "1001" in payload["target"]


def test_dashboard_altiplano_borrar_intent_sin_sesion_401(client):
    r = client.post(
        "/dashboard/altiplano/borrar-intent",
        json={"device_name": "BA_OLTA_X"},
    )
    assert r.status_code == 401


def test_dashboard_altiplano_borrar_intent_rejects_uuid(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/borrar-intent",
        json={"by_id": "550e8400-e29b-41d4-a716-446655440000"},
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "uuid" in (payload.get("message") or "").lower()


def test_dashboard_altiplano_borrar_intent_lote_ok(client, monkeypatch):
    import web.routes as routes

    def fake_borrar(_token, device_name, by_id, **kw):
        tgt = device_name or by_id or "x"
        return {"ok": True, "message": "ok", "target": str(tgt), "vno_steps": [], "cascade": True}

    monkeypatch.setattr(routes, "borrar_inp_con_cascada_vno", fake_borrar)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok-lote"

    r = client.post(
        "/dashboard/altiplano/borrar-intent-lote",
        json={"mode": "device", "items": ["BA_OLTA_A#1001#gpon", "BA_OLTA_B#1002#gpon"]},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["ok_count"] == 2
    assert payload["fail_count"] == 0
    assert len(payload["results"]) == 2


def test_dashboard_altiplano_borrar_intent_lote_sin_sesion_401(client):
    r = client.post(
        "/dashboard/altiplano/borrar-intent-lote",
        json={"mode": "device", "items": ["x"]},
    )
    assert r.status_code == 401


def test_dashboard_altiplano_crear_ont_connection_faltante_ok(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_crear(**kw):
        captured.update(kw)
        return {"ok": True, "target": "BA_OLTA_ES01_01-9-4-11#1001#gpon"}

    monkeypatch.setattr(routes, "crear_ont_connection_intent", fake_crear)
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok-inp"
    r = client.post(
        "/dashboard/altiplano/crear-ont-connection-faltante",
        json={
            "access_id": "1058485103",
            "error_detail": (
                "ont-connection intent does not exist for "
                "1001_BA_OLTA_ES01_01-9-4-11_GPON defined in L1 Scheduler"
            ),
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert captured["access_id"] == "1058485103"
    assert captured["ont"] == "11"
    assert captured["nbi_bearer_token"] == "tok-inp"


def test_dashboard_altiplano_sincronizar_intent_sin_sesion_401(client):
    r = client.post(
        "/dashboard/altiplano/sincronizar-intent",
        json={"device_name": "BA_OLTA_X#1001#gpon"},
    )
    assert r.status_code == 401


def test_dashboard_altiplano_actualizar_rn_sin_sesion_401(client):
    r = client.post(
        "/dashboard/altiplano/actualizar-required-network-state",
        json={"device_name": "BA_OLTA_X#1001#gpon", "required_network_state": "active"},
    )
    assert r.status_code == 401


def test_dashboard_altiplano_actualizar_rn_sin_valor_400(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"
    r = client.post(
        "/dashboard/altiplano/actualizar-required-network-state",
        json={"device_name": "BA_OLTA_X#1001#gpon"},
    )
    assert r.status_code == 400


def test_dashboard_altiplano_actualizar_tasa_profiles_ok(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "actualizar_tasa_composite_profiles_nbi",
        lambda *_a, **_kw: {
            "ok": True,
            "message": "Perfiles actualizados",
            "tasa_hsi": {
                "downstream_profile": "TASA_SH100MB_DN",
                "upstream_profile": "TASA_BW100MB_UP",
            },
        },
    )
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"
    r = client.post(
        "/dashboard/altiplano/actualizar-tasa-composite-profiles",
        json={
            "scope": "vno",
            "operator": "TASA",
            "target": "BA_OLTA_SF01_01-2-1-9#HSI-1501",
            "intent_type": "tasa-composite",
            "tasa_hsi": {
                "downstream_profile": "TASA_SH100MB_DN",
                "upstream_profile": "TASA_BW100MB_UP",
            },
        },
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_dashboard_altiplano_actualizar_tasa_profiles_con_credenciales_ui(
    client, monkeypatch
):
    import web.routes as routes

    captured = {}

    def fake_update(*_a, **kw):
        captured.update(kw)
        return {"ok": True, "message": "Perfiles actualizados"}

    monkeypatch.setattr(routes, "actualizar_tasa_composite_profiles_nbi", fake_update)
    monkeypatch.setattr(
        routes,
        "obtener_token_entorno_nbi",
        lambda *_a, **_k: "tok-ui",
    )

    r = client.post(
        "/dashboard/altiplano/actualizar-tasa-composite-profiles",
        json={
            "scope": "vno",
            "operator": "TASA",
            "target": "BA_OLTA_SF01_01-2-1-9#HSI-1501",
            "intent_type": "tasa-composite",
            "downstream_profile": "TASA_SH100MB_DN",
            "upstream_profile": "TASA_BW100MB_UP",
            "altiplano_user": "noc_user",
            "altiplano_password": "secret",
        },
    )
    assert r.status_code == 200
    assert captured.get("nbi_username") == "noc_user"
    assert captured.get("nbi_password") == "secret"


def test_dashboard_altiplano_actualizar_rn_by_id_con_hash_se_normaliza(client, monkeypatch):
    """Si by_id trae el target completo (#), no debe 400 por el regex de Access ID."""
    import web.routes as routes

    captured = {}

    def fake_rn(token, rn, **kw):
        captured["token"] = token
        captured["rn"] = rn
        captured.update(kw)
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "actualizar_required_network_state_ont_connection_inp", fake_rn)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok-rn-hash"

    tgt = "BA_OLTA_ES01_01-12-14-15#3001#gpon"
    r = client.post(
        "/dashboard/altiplano/actualizar-required-network-state",
        json={
            "device_name": tgt,
            "by_id": tgt,
            "required_network_state": "active",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert captured.get("access_id") is None
    assert captured.get("intent_uuid") is None
    assert captured.get("device_prefix") == tgt
    assert captured.get("rn") == "active"

    r2 = client.post(
        "/dashboard/altiplano/actualizar-required-network-state",
        json={"by_id": tgt, "required_network_state": "active"},
    )
    assert r2.status_code == 200
    assert captured.get("device_prefix") == tgt


def test_inp_mutacion_descarta_by_id_invalido_si_hay_target_con_hash(client, monkeypatch):
    """by_id con caracteres fuera del token pero device_name con # → se ignora by_id."""
    import web.routes as routes

    captured = {}

    def fake_rn(token, rn, **kw):
        captured.update(kw)
        return {"ok": True, "message": "ok", "matches": []}

    monkeypatch.setattr(routes, "actualizar_required_network_state_ont_connection_inp", fake_rn)

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    tgt = "BA_OLTA_ES01_01-12-14-15#3001#gpon"
    r = client.post(
        "/dashboard/altiplano/actualizar-required-network-state",
        json={
            "device_name": tgt,
            "by_id": "129322928\u200b",
            "required_network_state": "active",
        },
    )
    assert r.status_code == 200
    assert captured.get("access_id") is None
    assert captured.get("device_prefix") == tgt


def test_dashboard_altiplano_tasa_ejecutar_sin_sesion_401(client):
    r = client.post(
        "/dashboard/altiplano/vno/tasa/ejecutar",
        json={"api_id": "configure-create-ont", "variables": {}},
    )
    assert r.status_code == 401


def test_dashboard_altiplano_tasa_ejecutar_sin_credenciales_400(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "execute_tasa_postman_api",
        lambda *_a, **_k: {"ok": False, "message": "Credenciales Altiplano TASA no configuradas (env / .env)"},
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/vno/tasa/ejecutar",
        json={"api_id": "configure-create-ont", "variables": {"Device Name": "x"}},
    )
    assert r.status_code == 400


def test_dashboard_altiplano_cambiar_cto_sin_sesion_401(client):
    r = client.post(
        "/dashboard/altiplano/vno/cambiar-cto",
        json={"cto_id": "X", "access_id": "105"},
    )
    assert r.status_code == 401


def test_dashboard_altiplano_cambiar_cto_campos_vacios_400(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post("/dashboard/altiplano/vno/cambiar-cto", json={"cto_id": "", "access_id": ""})
    assert r.status_code == 400


def test_dashboard_altiplano_cambiar_cto_ok_200(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "enviar_cto_ftth_toolbox",
        lambda **kw: {
            "ok": True,
            "message": "Procesado",
            "toolbox_code": "0",
            "request": kw,
        },
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/vno/cambiar-cto",
        json={"cto_id": "04F5A122505D80", "access_id": "1059355238"},
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_dashboard_altiplano_tasa_ejecutar_ok_200(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "execute_tasa_postman_api",
        lambda *_a, **_k: {
            "ok": True,
            "message": "HTTP 204",
            "status_code": 204,
            "response_text": "",
            "request_method": "POST",
            "request_url": "https://h/p/b",
        },
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/vno/tasa/ejecutar",
        json={"api_id": "configure-create-ont", "variables": {"ONT": "1"}},
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
