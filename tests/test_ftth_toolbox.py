"""Tests del cliente Web ToolBox FTTH Norte (SendFTTH)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from services import ftth_toolbox as tb


def test_enviar_cto_requiere_campos():
    out = tb.enviar_cto_ftth_toolbox(cto_id="", access_id="105")
    assert out["ok"] is False
    assert "CTO" in out["message"]

    out2 = tb.enviar_cto_ftth_toolbox(cto_id="ABC", access_id="")
    assert out2["ok"] is False
    assert "Access" in out2["message"]


def test_enviar_cto_sin_credenciales(monkeypatch):
    monkeypatch.setattr(
        tb,
        "get_ftth_toolbox_config",
        lambda: {
            "base_url": "https://toolbox.example",
            "user": "",
            "password": "",
            "ally_atc_id": "8",
        },
    )
    out = tb.enviar_cto_ftth_toolbox(cto_id="X", access_id="105")
    assert out["ok"] is False
    assert "FTTH_TOOLBOX" in out["message"]


def test_parse_send_ftth_response_success():
    raw = json.dumps({"Code": "0", "Description": "OK", "RawResponse": None})
    parsed = tb._parse_send_ftth_response(raw)
    assert parsed["code"] == "0"
    assert parsed["description"] == "OK"


def test_enviar_cto_ok_con_sesion_mockeada(monkeypatch):
    monkeypatch.setattr(
        tb,
        "get_ftth_toolbox_config",
        lambda: {
            "base_url": "https://toolbox.example",
            "user": "u",
            "password": "p",
            "ally_atc_id": "8",
        },
    )

    class FakeSession:
        cookies = {"ci_session": "abc"}

        def __init__(self):
            self.headers = {}
            self.post_calls = []
            self.get_calls = []

        def post(self, url, **kwargs):
            self.post_calls.append((url, kwargs))
            res = MagicMock()
            if "login_ingreso" in url:
                res.status_code = 303
            else:
                res.status_code = 200
                res.text = json.dumps(
                    {"Code": "0", "Description": "Procesado", "RawResponse": None}
                )
            return res

        def get(self, url, **kwargs):
            self.get_calls.append(url)
            res = MagicMock()
            res.status_code = 200
            return res

    fake = FakeSession()

    def fake_session_factory(_base):
        return fake

    monkeypatch.setattr(tb, "_toolbox_session", fake_session_factory)

    out = tb.enviar_cto_ftth_toolbox(cto_id="04F5A122505D80", access_id="1059355238")
    assert out["ok"] is True
    assert out["toolbox_code"] == "0"
    assert len(fake.post_calls) == 2
    send_url, send_kw = fake.post_calls[1]
    assert "SendFTTH" in send_url
    assert send_kw["data"]["ctoid"] == "04F5A122505D80"
    assert send_kw["data"]["accessid"] == "1059355238"
    assert send_kw["data"]["tipo"] == "cto"
    assert send_kw["data"]["allyid"] == "8"


def test_enviar_cto_toolbox_error_code(monkeypatch):
    monkeypatch.setattr(
        tb,
        "get_ftth_toolbox_config",
        lambda: {
            "base_url": "https://toolbox.example",
            "user": "u",
            "password": "p",
            "ally_atc_id": "8",
        },
    )

    class FakeSession:
        cookies = {"x": "1"}

        def __init__(self):
            self.headers = {}

        def post(self, url, **kwargs):
            res = MagicMock()
            if "login" in url:
                res.status_code = 303
            else:
                res.status_code = 200
                res.text = json.dumps(
                    {
                        "Code": "98",
                        "Description": "HTTP Error: timeout",
                        "RawResponse": None,
                    }
                )
            return res

        def get(self, url, **kwargs):
            res = MagicMock()
            res.status_code = 200
            return res

    monkeypatch.setattr(tb, "_toolbox_session", lambda _b: FakeSession())

    out = tb.enviar_cto_ftth_toolbox(cto_id="CTO1", access_id="AID1")
    assert out["ok"] is False
    assert out["toolbox_code"] == "98"
    assert "timeout" in out["message"].lower()
