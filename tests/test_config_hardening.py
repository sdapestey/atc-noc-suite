import config as config_module


def test_get_db_pool_bounds_normalizes_min_max(monkeypatch):
    monkeypatch.setenv("DB_POOL_MIN", "8")
    monkeypatch.setenv("DB_POOL_MAX", "2")
    assert config_module.get_db_pool_bounds() == (8, 8)


def test_get_db_pool_bounds_defaults_for_invalid_values(monkeypatch):
    monkeypatch.setenv("DB_POOL_MIN", "abc")
    monkeypatch.setenv("DB_POOL_MAX", "0")
    assert config_module.get_db_pool_bounds() == (2, 2)


def test_get_db_pool_bounds_defaults_for_10_concurrent_profile(monkeypatch):
    monkeypatch.delenv("DB_POOL_MIN", raising=False)
    monkeypatch.delenv("DB_POOL_MAX", raising=False)
    assert config_module.get_db_pool_bounds() == (2, 10)


def test_dashboard_tree_cache_seconds_default_is_1800(monkeypatch):
    monkeypatch.delenv("DASHBOARD_TREE_CACHE_SECONDS", raising=False)
    assert config_module.get_dashboard_tree_cache_seconds_default() == 1800


def test_get_altiplano_inp_wide_search_http_timeout_s_default_and_floor(monkeypatch):
    monkeypatch.delenv("ALTIPLANO_INP_WIDE_SEARCH_HTTP_TIMEOUT_S", raising=False)
    assert config_module.get_altiplano_inp_wide_search_http_timeout_s() == 300
    monkeypatch.setenv("ALTIPLANO_INP_WIDE_SEARCH_HTTP_TIMEOUT_S", "10")
    assert config_module.get_altiplano_inp_wide_search_http_timeout_s() == 75


def test_get_orquestador_session_ttl_seconds_default_and_floor(monkeypatch):
    monkeypatch.delenv("ORQUESTADOR_SESSION_TTL_SECONDS", raising=False)
    assert config_module.get_orquestador_session_ttl_seconds() == 3600
    monkeypatch.setenv("ORQUESTADOR_SESSION_TTL_SECONDS", "30")
    assert config_module.get_orquestador_session_ttl_seconds() == 60


def test_get_consulta_altiplano_ui_cache_seconds_default_and_floor(monkeypatch):
    monkeypatch.delenv("CONSULTA_ALTIPLANO_UI_CACHE_SECONDS", raising=False)
    assert config_module.get_consulta_altiplano_ui_cache_seconds() == 600
    monkeypatch.setenv("CONSULTA_ALTIPLANO_UI_CACHE_SECONDS", "30")
    assert config_module.get_consulta_altiplano_ui_cache_seconds() == 60

