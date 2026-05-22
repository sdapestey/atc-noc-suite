import importlib.util
from pathlib import Path

import altiplano


def _load_sn_altiplano():
    path = Path(__file__).resolve().parents[1] / "services" / "sn_altiplano.py"
    spec = importlib.util.spec_from_file_location("sn_altiplano", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_channel_partition_from_tasa_ont():
    assert (
        altiplano._channel_partition_name_from_object_name("BA_OLTA_SF01_01-2-1-9")
        == "BA_OLTA_SF01_01-2-1_CPART_GPON"
    )
    assert altiplano._pon_index_from_object_name("BA_OLTA_SF01_01-2-1-9") == "1"


def test_channel_partition_from_directv_ont():
    assert (
        altiplano._channel_partition_name_from_object_name("BA_OLTA_SF01_01-2-1-35")
        == "BA_OLTA_SF01_01-2-1_CPART_GPON"
    )


def test_cambiar_admin_status_pon_posts_channel_partition(monkeypatch):
    captured = {}

    def fake_post(url, auth_url, payload, **kwargs):
        captured["url"] = url
        captured["payload"] = payload
        return {"ok": True, "status_code": 200}

    monkeypatch.setattr(altiplano, "_http_post_altiplano_expect_ok", fake_post)
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("10.200.3.100", "32443", "inp-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_operator_credentials",
        lambda _op: ("u", "p"),
    )

    out = altiplano.cambiar_admin_status_pon(
        "1051849629",
        "BA_OLTA_SF01_01-2-1-9",
        "TASA",
        "LOCKED",
    )
    assert out["ok"] is True
    assert "ChannelPartition" in captured["url"]
    assert "BA_OLTA_SF01_01-2-1_CPART_GPON" in captured["url"]
    assert captured["payload"] == {"adminStatus": "LOCKED"}
