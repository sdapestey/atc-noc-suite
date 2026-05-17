"""Catálogo Postman TASA (Orquestador VNO)."""

from pathlib import Path

from services import tasa_postman_catalog as cat


def test_load_tasa_postman_api_list_default_file():
    apis, err = cat.load_tasa_postman_api_list()
    assert err is None
    labels = [a["label"] for a in apis]
    assert labels == [
        "Configure / Create ONT",
        "Configure / Create Services",
        "Modify / Modify Serial Number",
        "Modify / Modify Profiles",
        "Unconfigure / Delete Services",
        "Unconfigure / Delete ONT",
    ]
    assert all(a["id"] for a in apis)
    assert all(a["method"] for a in apis)
    assert apis[0]["url_raw"]


def test_load_tasa_postman_api_list_missing_file():
    apis, err = cat.load_tasa_postman_api_list(Path("/nonexistent/tasa.json"))
    assert apis == []
    assert err is not None
    assert "No se pudo leer" in err or "lectura" in err.lower()


def test_wizard_merges_create_ont_and_services_into_one_entry():
    apis, err = cat.load_tasa_postman_api_list()
    assert err is None
    w = cat.apply_tasa_wizard_api_list_overrides(apis)
    assert w[0]["id"] == cat.TASA_ONT_PLUS_SERVICES_API_ID
    assert w[0]["label"] == "Configure / Create ONT + Services"
    ids = [a["id"] for a in w]
    assert cat.TASA_ONT_API_ID not in ids
    assert cat.TASA_SERVICES_API_ID not in ids
    fv = w[0]["form_variables"]
    assert "Serial Number" in fv
    assert "SVLAN" in fv
    assert "CVLAN" in fv


def test_build_tasa_vno_wizard_context_includes_composite():
    ctx = cat.build_tasa_vno_wizard_context()
    assert ctx["tasa_postman_collection_name"]
    assert isinstance(ctx["tasa_postman_apis"], list)
    assert "tasa_nbi_entorno_label" in ctx
    assert ctx["tasa_nbi_host"]
    if ctx.get("tasa_postman_catalog_error"):
        return
    ids = [a["id"] for a in ctx["tasa_postman_apis"]]
    assert cat.TASA_ONT_PLUS_SERVICES_API_ID in ids
    assert cat.TASA_ONT_API_ID not in ids


def test_create_ont_has_form_variables_and_headers():
    apis, err = cat.load_tasa_postman_api_list()
    assert err is None
    ont = apis[0]
    assert ont["id"] == "configure-create-ont"
    assert "Device Name" in ont["form_variables"]
    assert "Serial Number" in ont["form_variables"]
    assert "protocol" not in ont["form_variables"]
    assert ont["body_raw"]
    assert any(h.get("key") == "Accept" for h in ont["headers"])


def test_get_tasa_postman_api_by_id():
    spec = cat.get_tasa_postman_api_by_id("unconfigure-delete-ont")
    assert spec is not None
    assert spec["method"] == "POST"
    assert spec["request_name"] == "Delete ONT"
    assert cat.get_tasa_postman_api_by_id("no-existe") is None
