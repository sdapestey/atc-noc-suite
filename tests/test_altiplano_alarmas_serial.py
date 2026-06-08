def test_filter_alarmas_por_serial_ont_descarta_serial_distinto():
    import altiplano

    alarmas = [
        {
            "type": "onu-loss-of-phy-layer",
            "text": "Serial-Number=SDMC692F8410, Reg-ID=, CT-Name=CT_X",
        },
        {
            "type": "absence-of-phy",
            "text": "Serial-Number=ASKY009275C8, Reg-ID=, CT-Name=CT_Y",
        },
        {"type": "other", "text": "sin serial en texto"},
    ]
    out = altiplano.filter_alarmas_por_serial_ont(alarmas, "ASKY009275C8")
    assert len(out) == 2
    assert out[0]["type"] == "absence-of-phy"
    assert out[1]["type"] == "other"


def test_reconcile_ont_nv_oper_status_stale_inp_down_con_potencia():
    import altiplano

    out = {
        "tx": 2.2,
        "rx": -19.6,
        "sn": "ASKY009275C8",
        "oper": "DOWN",
        "health": "faulty",
    }
    altiplano._reconcile_ont_nv_oper_status(
        out,
        "1059418526",
        {"oper": "DOWN", "admin": "UNLOCKED", "ema_serial": "SDMC692F8410"},
    )
    assert out["oper"] == "UP"
    assert out["health"] == "Healthy"
