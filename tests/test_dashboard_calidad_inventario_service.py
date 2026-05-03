import services.dashboard_calidad_inventario as calidad


def test_norm_limit_bounds():
    assert calidad._norm_limit(None) == 500
    assert calidad._norm_limit("x") == 500
    assert calidad._norm_limit(0) == 1
    assert calidad._norm_limit(999999) == 5000


def test_missing_serial_rule_has_ui_description():
    desc = calidad.RULES["missing_serial_match"].get("description", "")
    assert desc
    assert "ONT-connection" in desc
    assert "altiplano.serial" in desc


def test_missing_olt_rule_has_ui_description():
    desc = calidad.RULES["missing_olt_match"].get("description", "")
    assert desc
    assert "ONT-connection" in desc
    assert "ConnectMaster" in desc
    assert "inventory_olt_occupation" not in desc


def test_missing_path_atc_rule_has_ui_description():
    desc = calidad.RULES["missing_path_atc"].get("description", "")
    assert desc
    assert "path ATC" in desc
    assert "ConnectMaster" in desc


def test_blank_serial_rule_has_ui_description():
    desc = calidad.RULES["blank_serial_number"].get("description", "")
    assert desc
    assert "ConnectMaster" in desc
    assert "Altiplano" in desc
    assert "ONT-connection" in desc


def test_norm_base_status():
    assert calidad._norm_base_status("IN SERVICE") == "IN SERVICE"
    assert calidad._norm_base_status("reserved") == "RESERVED"
    assert calidad._norm_base_status("TO BE DELETED") == "TO BE DELETED"
    assert calidad._norm_base_status("free") == "FREE"
    assert calidad._norm_base_status("unknown") == ""


def test_export_dashboard_calidad_inventario_csv_uses_findings(monkeypatch):
    monkeypatch.setattr(
        calidad,
        "dashboard_calidad_inventario_hallazgos",
        lambda **_kwargs: {
            "findings": [
                {
                    "regla": "Sin match en OLT",
                    "access_id": "123",
                    "base_status": "IN SERVICE",
                    "path_atc": "TG01-RATC-0-0001",
                    "cto": "TG01-FATC-1-0001",
                    "operador": "1001",
                }
            ]
        },
    )
    csv_text = calidad.export_dashboard_calidad_inventario_csv(regla="missing_olt_match")
    assert "regla,access_id,estado_base,path_atc,cto,operador" in csv_text
    assert "Sin match en OLT,123,IN SERVICE,TG01-RATC-0-0001,TG01-FATC-1-0001,1001" in csv_text
