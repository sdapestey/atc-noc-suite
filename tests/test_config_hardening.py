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

