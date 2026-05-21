import services.dashboard_calidad_inventario as calidad


def test_norm_limit_bounds():
    assert calidad._norm_limit(None) == calidad.DEFAULT_PAGE_SIZE
    assert calidad._norm_limit("x") == calidad.DEFAULT_PAGE_SIZE
    assert calidad._norm_limit(0) == 1
    assert calidad._norm_limit(999999) == calidad.MAX_PAGE_SIZE


def test_rules_include_superset_parity():
    assert "casos_rotos_rack" in calidad.RULES
    assert "fat_sin_tag_nfc" in calidad.RULES
    assert "fat_tag_nfc_duplicado" in calidad.RULES
    assert len(calidad.RULES) == 7


def test_fat_nfc_duplicados_tabla_order_by_select_list_compatible():
    """SELECT DISTINCT exige que ORDER BY use columnas del SELECT (posiciones)."""
    import inspect

    src = inspect.getsource(calidad.dashboard_calidad_fat_nfc_duplicados_tabla)
    assert "ORDER BY 2, 1" in src
    assert "ORDER BY nfc_tag_id" not in src


def test_historico_days_clamped(monkeypatch):
    class _Cur:
        def execute(self, *_a, **_k):
            return None

        def fetchall(self):
            return []

    from contextlib import contextmanager

    @contextmanager
    def _fake_db():
        yield _Cur()

    monkeypatch.setattr(calidad, "db_cursor", _fake_db)
    payload = calidad.dashboard_calidad_inventario_historico(days=9999)
    assert payload["days"] == 365
    payload_min = calidad.dashboard_calidad_inventario_historico(days=1)
    assert payload_min["days"] == 7


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
