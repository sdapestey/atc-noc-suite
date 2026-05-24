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
_lock_calidad_conciliacion = threading.Lock()
_lock_inventario_estadisticas = threading.Lock()
_lock_cto_potencias = threading.Lock()
_lock_olt_lt = threading.Lock()
_lock_historico_potencias = threading.Lock()
_rama = {"payload": None, "expires_at": 0.0}
_olt = {"payload": None, "expires_at": 0.0}
_rama_potencias = {}
_rama_inventario = {}
_cto_potencias: dict[str, dict] = {}
_olt_lt: dict[str, dict] = {}
_historico_potencias: dict[str, dict] = {}
_calidad_resumen = {"payload": None, "expires_at": 0.0}
_calidad_conciliacion = {"payload": None, "expires_at": 0.0}
_inventario_estadisticas: dict[str, dict] = {}


def _get_cached_dict_entry(
    store: dict,
    lock: threading.Lock,
    ttl_seconds: int,
    key: str,
    factory: Callable[[], T],
) -> T:
    """Entrada genérica en dict por clave (CTO, LT, histórico, etc.)."""
    if ttl_seconds <= 0:
        return factory()
    norm = str(key or "").strip()
    if not norm:
        return factory()
    with lock:
        now = time.monotonic()
        entry = store.get(norm)
        if entry is not None and now < entry["expires_at"]:
            return entry["payload"]
        data = factory()
        store[norm] = {"payload": data, "expires_at": now + ttl_seconds}
        return data


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


def get_cached_cto_potencias(ttl_seconds: int, cto_key: str, factory: Callable[[], T]) -> T:
    """Cachea potencias Altiplano por CTO (dashboards RAMA/OLT/consulta)."""
    return _get_cached_dict_entry(_cto_potencias, _lock_cto_potencias, ttl_seconds, cto_key, factory)


def get_cached_olt_lt(ttl_seconds: int, lt_key: str, factory: Callable[[], T]) -> T:
    """Cachea inventario estructural bajo un LT (dashboard OLT)."""
    return _get_cached_dict_entry(_olt_lt, _lock_olt_lt, ttl_seconds, lt_key, factory)


def get_cached_historico_potencias(
    ttl_seconds: int,
    cache_key: str,
    factory: Callable[[], T],
) -> T:
    """Cachea payload de histórico por rama + rango de días."""
    return _get_cached_dict_entry(
        _historico_potencias, _lock_historico_potencias, ttl_seconds, cache_key, factory
    )


def get_cached_calidad_conciliacion(ttl_seconds: int, factory: Callable[[], T]) -> T:
    """Cachea conteos de conciliación CM vs Altiplano."""
    if ttl_seconds <= 0:
        return factory()
    with _lock_calidad_conciliacion:
        now = time.monotonic()
        if _calidad_conciliacion["payload"] is not None and now < _calidad_conciliacion["expires_at"]:
            return _calidad_conciliacion["payload"]
        data = factory()
        _calidad_conciliacion["payload"] = data
        _calidad_conciliacion["expires_at"] = now + ttl_seconds
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


def get_cached_inventario_estadisticas(
    ttl_seconds: int,
    granularity: str,
    factory: Callable[[], T],
) -> T:
    """Cachea estadísticas de altas/bajas por granularidad (día / mes / año)."""
    if ttl_seconds <= 0:
        return factory()
    key = f"gran:{granularity}"
    with _lock_inventario_estadisticas:
        now = time.monotonic()
        entry = _inventario_estadisticas.get(key)
        if entry is not None and now < entry["expires_at"]:
            return entry["payload"]
        data = factory()
        _inventario_estadisticas[key] = {"payload": data, "expires_at": now + ttl_seconds}
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
    with _lock_inventario_estadisticas:
        _inventario_estadisticas.clear()
    with _lock_cto_potencias:
        _cto_potencias.clear()
    with _lock_olt_lt:
        _olt_lt.clear()
    with _lock_historico_potencias:
        _historico_potencias.clear()
    with _lock_calidad_conciliacion:
        _calidad_conciliacion["payload"] = None
        _calidad_conciliacion["expires_at"] = 0.0
