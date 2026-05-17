"""Ejecución de requests TASA desde catálogo Postman."""

from services import tasa_postman_execute as ex


def test_execute_tasa_postman_api_happy_path(monkeypatch):
    monkeypatch.setattr(ex, "get_altiplano_operator_credentials", lambda _op: ("u", "p"))
    monkeypatch.setattr(ex, "get_altiplano_nbi_target", lambda _op: ("10.0.0.5", "32443", "tasa-altiplano-ac"))
    monkeypatch.setattr(ex, "obtener_token_entorno_nbi", lambda *_a, **_k: "tok-tasa")

    calls: list[tuple[str, str]] = []

    class FakeResp:
        status_code = 204
        text = ""

    def fake_request(method, url, **_kw):
        calls.append((method, url))
        return FakeResp()

    monkeypatch.setattr(ex.requests, "request", fake_request)

    out = ex.execute_tasa_postman_api(
        "configure-create-ont",
        {
            "Device Name": "BA_OLTA_X",
            "LT": "1",
            "PON": "1",
            "ONT": "2",
            "Serial Number": "ALCL00000002",
        },
    )
    assert out["ok"] is True
    assert calls[0][0] == "POST"
    assert "10.0.0.5:32443" in calls[0][1]
    assert "/tasa-altiplano-ac/rest/restconf" in calls[0][1]


def test_execute_fills_default_serial_when_empty(monkeypatch):
    monkeypatch.setattr(ex, "get_altiplano_operator_credentials", lambda _op: ("u", "p"))
    monkeypatch.setattr(ex, "get_altiplano_nbi_target", lambda _op: ("10.0.0.5", "32443", "tasa-altiplano-ac"))
    monkeypatch.setattr(ex, "obtener_token_entorno_nbi", lambda *_a, **_k: "tok-tasa")

    captured_bodies: list[dict] = []

    class FakeResp:
        status_code = 204
        text = ""

    def fake_request(method, url, **kw):
        if kw.get("json"):
            captured_bodies.append(kw["json"])
        return FakeResp()

    monkeypatch.setattr(ex.requests, "request", fake_request)

    out = ex.execute_tasa_postman_api(
        "configure-create-ont",
        {
            "Device Name": "BA_OLTA_X",
            "LT": "10",
            "PON": "6",
            "ONT": "99",
            "Serial Number": "",
        },
    )
    assert out["ok"] is True
    assert captured_bodies
    sn = (
        captured_bodies[0]
        .get("ibn:intent", {})
        .get("intent-specific-data", {})
        .get("ont:ont", {})
        .get("expected-serial-number")
    )
    assert sn == "ALCL00100699"


def test_execute_rejects_bad_api_id():
    out = ex.execute_tasa_postman_api("../../../etc/passwd", {})
    assert out["ok"] is False
    assert "api_id" in (out.get("message") or "").lower()


def test_execute_ont_plus_services_runs_both_steps(monkeypatch):
    monkeypatch.setattr(ex, "get_altiplano_operator_credentials", lambda _op: ("u", "p"))
    monkeypatch.setattr(ex, "get_altiplano_nbi_target", lambda _op: ("10.0.0.5", "32443", "tasa-altiplano-ac"))
    monkeypatch.setattr(ex, "obtener_token_entorno_nbi", lambda *_a, **_k: "tok-tasa")

    calls: list[str] = []

    class FakeResp:
        status_code = 200
        text = "{}"

    def fake_request(method, url, **_kw):
        calls.append(url)
        return FakeResp()

    monkeypatch.setattr(ex.requests, "request", fake_request)

    out = ex.execute_tasa_postman_api(
        "configure-create-ont-plus-services",
        {
            "Device Name": "BA_OLTA_X",
            "LT": "1",
            "PON": "1",
            "ONT": "2",
            "Serial Number": "ALCL00000002",
            "SVLAN": "100",
            "CVLAN": "200",
        },
    )
    assert out["ok"] is True
    assert len(calls) == 2
    assert all("/tasa-altiplano-ac/rest/restconf" in u for u in calls)

