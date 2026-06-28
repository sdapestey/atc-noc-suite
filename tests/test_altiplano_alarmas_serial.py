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


def test_filter_alarmas_por_recurso_ont_descarta_onu_colindante():
    import altiplano

    ont = "BA_OLTA_ES01_01-1-1-1"
    alarmas = [
        {
            "type": "absence-of-phy",
            "resource": "interface:BA_OLTA_ES01_01.LT1:v7~BA_OLTA_ES01_01-1-1-100_GPON",
            "text": "Serial-Number=, Reg-ID=, CT-Name=CT_X",
        },
        {
            "type": "onu-dying-gasp",
            "resource": "interface:BA_OLTA_ES01_01.LT1:v1~BA_OLTA_ES01_01-1-1-1_GPON",
            "text": "Serial-Number=MSTC8CBFF3AF, Reg-ID=, CT-Name=CT_X",
        },
    ]
    out = altiplano.filter_alarmas_para_ont(alarmas, "MSTC8CBFF3AF", ont)
    assert len(out) == 1
    assert out[0]["type"] == "onu-dying-gasp"


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
