"""Tests del caché TTL de árboles de dashboard."""
import pytest

from services import dashboard_cache as dc


@pytest.fixture(autouse=True)
def clear_tree_caches():
    dc.reset_dashboard_tree_caches()
    yield
    dc.reset_dashboard_tree_caches()


def test_ttl_zero_calls_factory_each_time(monkeypatch):
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return {"id": calls["n"]}

    a = dc.get_cached_rama(0, factory)
    b = dc.get_cached_rama(0, factory)
    assert a["id"] == 1
    assert b["id"] == 2
    assert calls["n"] == 2


def test_ttl_reuses_within_window(monkeypatch):
    t = {"v": 0.0}
    monkeypatch.setattr(dc.time, "monotonic", lambda: t["v"])

    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return {"x": calls["n"]}

    a = dc.get_cached_olt(60, factory)
    t["v"] += 30
    b = dc.get_cached_olt(60, factory)
    assert a is b
    assert calls["n"] == 1


def test_ttl_refreshes_after_expiry(monkeypatch):
    t = {"v": 1000.0}
    monkeypatch.setattr(dc.time, "monotonic", lambda: t["v"])

    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return calls["n"]

    assert dc.get_cached_rama(10, factory) == 1
    t["v"] += 11
    assert dc.get_cached_rama(10, factory) == 2
    assert calls["n"] == 2
