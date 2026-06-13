"""Estadísticas Altiplano INP — conteos y ruta JSON."""
import altiplano as ap
from services.estadisticas_altiplano import dashboard_estadisticas_altiplano_inp


def test_contar_ont_connection_inp_search_intents_reads_total_count(monkeypatch):
    calls = []

    class FakeRes:
        status_code = 200
        text = '{"ibn:output":{"total-count":42,"page-size":1}}'

    def fake_post(url, headers=None, json=None, verify=False, timeout=None):
        calls.append({"url": url, "json": json})
        return FakeRes()

    monkeypatch.setattr(ap.requests, "post", fake_post)
    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("h", "32443", "inp-ac"))
    monkeypatch.setattr(
        ap,
        "_inp_search_intents_operation_url",
        lambda _base: "https://h:32443/inp-ac/rest/restconf/operations/ibn:search-intents",
    )

    out = ap.contar_ont_connection_inp_search_intents(
        "tok",
        filter_required_network_state=["not-present"],
        filter_alignment_state=["misaligned"],
    )
    assert out["ok"] is True
    assert out["count"] == 42
    flt = calls[0]["json"]["ibn:search-intents"]["filter"]
    assert flt["required-network-state"] == ["delete"]
    assert flt["aligned"] == "false"


def test_inp_bearer_token_uses_altiplano_credentials(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "services.estadisticas_altiplano.get_altiplano_credentials",
        lambda: ("svc_user", "svc_pass"),
    )

    def fake_token(entorno, user, pwd, **kwargs):
        captured["entorno"] = entorno
        captured["user"] = user
        captured["pwd"] = pwd
        return "tok-env"

    monkeypatch.setattr("services.estadisticas_altiplano.obtener_token_entorno_nbi", fake_token)

    from services.estadisticas_altiplano import _inp_bearer_token

    token, err = _inp_bearer_token()
    assert token == "tok-env"
    assert err is None
    assert captured == {"entorno": "INP", "user": "svc_user", "pwd": "svc_pass"}


def test_dashboard_estadisticas_altiplano_inp_aggregates_sections(monkeypatch):
    monkeypatch.setattr(
        "services.estadisticas_altiplano._inp_bearer_token",
        lambda: ("tok", None),
    )

    def fake_count(token, *, required_network_state, alignment_state, timeout_s):
        key = (
            ",".join(required_network_state or []),
            ",".join(alignment_state or []),
        )
        totals = {
            ("active", ""): 100,
            ("suspended", ""): 20,
            ("not-present", ""): 5,
            ("", "aligned"): 80,
            ("", "misaligned"): 25,
            ("not-present", "misaligned"): 3,
            ("not-present", "aligned"): 2,
            ("active", "misaligned"): 10,
            ("suspended", "misaligned"): 4,
        }
        return {"ok": True, "count": totals.get(key, 0), "message": ""}

    monkeypatch.setattr("services.estadisticas_altiplano._count_one", fake_count)

    payload = dashboard_estadisticas_altiplano_inp(cache_seconds=0)
    assert payload["ok"] is True
    assert len(payload["sections"]) == 3
    rn = payload["sections"][0]
    assert rn["id"] == "required_network_state"
    assert rn["cards"][0]["count"] == 100
    combos = payload["sections"][2]
    assert combos["cards"][1]["title"] == "Not present + Misaligned"
    assert combos["cards"][1]["count"] == 3


def test_dashboard_estadisticas_altiplano_json_route(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_service(*, refresh=False):
        captured["refresh"] = refresh
        return {
            "ok": True,
            "sections": [{"id": "required_network_state", "title": "RN", "cards": []}],
        }

    monkeypatch.setattr(routes, "dashboard_estadisticas_altiplano_inp", fake_service)
    r = client.get("/dashboard/estadisticas/altiplano.json")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert captured.get("refresh") is False

    r2 = client.get("/dashboard/estadisticas/altiplano.json?refresh=1")
    assert r2.status_code == 200
    assert captured.get("refresh") is True


def test_dashboard_estadisticas_get_includes_altiplano_tab(client):
    r = client.get("/dashboard/estadisticas")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'data-tab="altiplano"' in html
    assert "Altiplano</button>" in html
    assert "dashboard-estadisticas-altiplano.js" in html
    assert (
        'id="panel-altiplano" class="panel calidad-panel calidad-panel--altiplano card suite-index-card" '
        'role="tabpanel" aria-labelledby="tab-altiplano" hidden'
    ) in html
