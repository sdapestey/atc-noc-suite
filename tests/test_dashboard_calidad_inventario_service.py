import services.dashboard_calidad_inventario as calidad


def test_norm_limit_bounds():
    assert calidad._norm_limit(None) == 500
    assert calidad._norm_limit("x") == 500
    assert calidad._norm_limit(0) == 1
    assert calidad._norm_limit(999999) == 5000


def test_export_dashboard_calidad_inventario_csv_uses_findings(monkeypatch):
    monkeypatch.setattr(
        calidad,
        "dashboard_calidad_inventario_hallazgos",
        lambda **_kwargs: {
            "findings": [
                {
                    "regla": "Sin match en OLT",
                    "access_id": "123",
                    "path_atc": "TG01-RATC-0-0001",
                    "cto": "TG01-FATC-1-0001",
                    "operador": "1001",
                    "severidad": "alta",
                }
            ]
        },
    )
    csv_text = calidad.export_dashboard_calidad_inventario_csv(regla="missing_olt_match")
    assert "regla,access_id,path_atc,cto,operador,severidad" in csv_text
    assert "Sin match en OLT,123,TG01-RATC-0-0001,TG01-FATC-1-0001,1001,alta" in csv_text
