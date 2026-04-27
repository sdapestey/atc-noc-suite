"""Caché en memoria con TTL para dashboards y consultas de potencia."""
import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")

_lock_rama = threading.Lock()
_lock_olt = threading.Lock()
_lock_rama_potencias = threading.Lock()
_rama = {"payload": None, "expires_at": 0.0}
_olt = {"payload": None, "expires_at": 0.0}
_rama_potencias = {}


def get_cached_rama(ttl_seconds: int, factory: Callable[[], T]) -> T:
    """Devuelve payload cacheado del árbol RAMA o lo recalcula.

    Args:
        ttl_seconds: Tiempo de vida en segundos. Si es `<= 0`, no cachea.
        factory: Función que construye el payload fresco.
    """
    if ttl_seconds <= 0:
        return factory()
    with _lock_rama:
        now = time.monotonic()
        if _rama["payload"] is not None and now < _rama["expires_at"]:
            return _rama["payload"]
        data = factory()
        _rama["payload"] = data
        _rama["expires_at"] = time.monotonic() + ttl_seconds
        return data


def get_cached_olt(ttl_seconds: int, factory: Callable[[], T]) -> T:
    """Devuelve payload cacheado del árbol OLT o lo recalcula.

    Args:
        ttl_seconds: Tiempo de vida en segundos. Si es `<= 0`, no cachea.
        factory: Función que construye el payload fresco.
    """
    if ttl_seconds <= 0:
        return factory()
    with _lock_olt:
        now = time.monotonic()
        if _olt["payload"] is not None and now < _olt["expires_at"]:
            return _olt["payload"]
        data = factory()
        _olt["payload"] = data
        _olt["expires_at"] = time.monotonic() + ttl_seconds
        return data


def get_cached_rama_potencias(ttl_seconds: int, rama_key: str, factory: Callable[[], T]) -> T:
    """Cachea por RAMA resultados de consulta de potencias."""
    if ttl_seconds <= 0:
        return factory()
    key = str(rama_key or "").strip().upper()
    if not key:
        return factory()
    with _lock_rama_potencias:
        now = time.monotonic()
        entry = _rama_potencias.get(key)
        if entry is not None and now < entry["expires_at"]:
            return entry["payload"]
        data = factory()
        _rama_potencias[key] = {"payload": data, "expires_at": now + ttl_seconds}
        return data


def reset_dashboard_tree_caches() -> None:
    """Solo tests: vacía entradas (no hay invalidación manual en producción)."""
    with _lock_rama:
        _rama["payload"] = None
        _rama["expires_at"] = 0.0
    with _lock_olt:
        _olt["payload"] = None
        _olt["expires_at"] = 0.0
    with _lock_rama_potencias:
        _rama_potencias.clear()
