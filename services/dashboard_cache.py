"""Caché en memoria con TTL para dashboards y consultas de potencia."""
import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_lock_rama = threading.Lock()
_lock_olt = threading.Lock()
_lock_rama_potencias = threading.Lock()
_lock_rama_inventario = threading.Lock()
_lock_calidad_resumen = threading.Lock()
_rama = {"payload": None, "expires_at": 0.0}
_olt = {"payload": None, "expires_at": 0.0}
_rama_potencias = {}
_rama_inventario = {}
_calidad_resumen = {"payload": None, "expires_at": 0.0}


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


def get_cached_rama_inventario(ttl_seconds: int, rama_key: str, factory: Callable[[], T]) -> T:
    """Cachea por RAMA resultados de inventario estructural."""
    if ttl_seconds <= 0:
        return factory()
    key = str(rama_key or "").strip().upper()
    if not key:
        return factory()
    with _lock_rama_inventario:
        now = time.monotonic()
        entry = _rama_inventario.get(key)
        if entry is not None and now < entry["expires_at"]:
            return entry["payload"]
        data = factory()
        _rama_inventario[key] = {"payload": data, "expires_at": now + ttl_seconds}
        return data


def get_cached_calidad_resumen(ttl_seconds: int, factory: Callable[[], T]) -> T:
    """Devuelve KPIs cacheados del dashboard de calidad o los recalcula."""
    if ttl_seconds <= 0:
        return factory()
    with _lock_calidad_resumen:
        now = time.monotonic()
        if _calidad_resumen["payload"] is not None and now < _calidad_resumen["expires_at"]:
            return _calidad_resumen["payload"]
        data = factory()
        _calidad_resumen["payload"] = data
        _calidad_resumen["expires_at"] = now + ttl_seconds
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
    with _lock_rama_inventario:
        _rama_inventario.clear()
    with _lock_calidad_resumen:
        _calidad_resumen["payload"] = None
        _calidad_resumen["expires_at"] = 0.0
