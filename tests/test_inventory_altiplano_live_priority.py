def test_priorizar_altiplano_en_detalle_ont_y_sn(monkeypatch):
    from services import inventory as inv

    monkeypatch.setattr(
        inv,
        "_live_altiplano_device_y_expected_sn",
        lambda aid, **kw: (
            "BA_OLTA_ES01_01-10-12-18",
            "ASKY0078C8B9",
            1001,
        ),
    )

    det = {
        "AID": "1059355238",
        "Status": "IN SERVICE",
        "ONT": "BA_OLTA_ES01_01-10-12-3",
        "SN": "SDMCFDF2CB41",
    }
    out = inv._priorizar_altiplano_en_detalle(det)
    assert out["ONT"] == "BA_OLTA_ES01_01-10-12-18"
    assert out["SN"] == "ASKY0078C8B9"


def test_priorizar_altiplano_en_detalle_conserva_postgres_si_sin_lectura(monkeypatch):
    from services import inventory as inv

    monkeypatch.setattr(
        inv,
        "_live_altiplano_device_y_expected_sn",
        lambda aid, **kw: (None, None, None),
    )

    det = {
        "AID": "1059355238",
        "Status": "IN SERVICE",
        "ONT": "BA_OLTA_ES01_01-10-12-3",
        "SN": "ASKY0078C8B9",
    }
    out = inv._priorizar_altiplano_en_detalle(det)
    assert out["ONT"] == "BA_OLTA_ES01_01-10-12-3"
    assert out["SN"] == "ASKY0078C8B9"


def test_priorizar_altiplano_en_detalle_free_no_consulta(monkeypatch):
    from services import inventory as inv

    called = []

    def fake_live(*a, **k):
        called.append(1)
        return "x", "y", 1

    monkeypatch.setattr(inv, "_live_altiplano_device_y_expected_sn", fake_live)
    det = {"AID": "1", "Status": "FREE", "ONT": "—", "SN": "—"}
    inv._priorizar_altiplano_en_detalle(det)
    assert called == []
