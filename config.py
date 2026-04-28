"""
Configuración centralizada. Secretos vía variables de entorno o archivo `.env`.
"""
import os
from pathlib import Path
from urllib.parse import urlparse

# Cargar .env antes de leer variables (no falla si python-dotenv no está)
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


def _database_from_url(url: str) -> dict:
    """Parsea `DATABASE_URL` y devuelve parámetros compatibles con psycopg2."""
    p = urlparse(url)
    if p.scheme not in ("postgresql", "postgres"):
        raise ValueError("DATABASE_URL debe ser postgresql://...")
    path = (p.path or "").lstrip("/")
    return {
        "dbname": path or "postgres",
        "user": p.username or "",
        "password": p.password or "",
        "host": p.hostname or "localhost",
        "port": str(p.port or 5432),
    }


def get_db_params() -> dict:
    """Parámetros para psycopg2.connect / connection pool."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return _database_from_url(url)
    return {
        "dbname": os.environ.get("DB_NAME", "postgres"),
        "user": os.environ.get("DB_USER", "om_read"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
    }


def get_altiplano_credentials() -> tuple[str, str]:
    """Credenciales globales de Altiplano (fallback por defecto)."""
    user = os.environ.get("ALTIPLANO_USER", "")
    password = os.environ.get("ALTIPLANO_PASSWORD", "")
    return user, password


def get_altiplano_operator_credentials(operator: str) -> tuple[str, str]:
    """
    Credenciales por operador para acciones NBI (como cambio de SN).
    Fallback: credenciales globales ALTIPLANO_USER / ALTIPLANO_PASSWORD.
    """
    op = (operator or "").strip().upper()
    op_key = {
        "TASA": "TASA",
        "DIRECTV": "DTV",
        "METROTEL": "METRO",
        "IPLAN": "IPLAN",
        "ATC": "ATC",
        "SION": "SION",
        "INP": "INP",
    }.get(op)
    if not op_key:
        return get_altiplano_credentials()
    user = os.environ.get(f"ALTIPLANO_{op_key}_USER", "").strip()
    password = os.environ.get(f"ALTIPLANO_{op_key}_PASSWORD", "").strip()
    if user and password:
        return user, password
    return get_altiplano_credentials()


def get_altiplano_nbi_target(operator: str) -> tuple[str, str, str]:
    """
    Endpoint NBI por operador (host, port, base_url).
    """
    op = (operator or "").strip().upper()
    defaults = {
        "INP": ("10.200.3.100", "32443", "inp-altiplano-ac"),
        "TASA": ("10.200.4.101", "32443", "tasa-altiplano-ac"),
        "DIRECTV": ("10.200.7.107", "32443", "dtv-altiplano-ac"),
        "METROTEL": ("10.200.5.102", "32443", "metro-altiplano-ac"),
        "IPLAN": ("10.200.5.103", "32444", "iplan-altiplano-ac"),
        "ATC": ("10.200.5.105", "32446", "atc-altiplano-ac"),
        "SION": ("10.200.5.104", "32445", "sion-altiplano-ac"),
    }
    host, port, base = defaults.get(op, ("", "", ""))
    env_prefix = {
        "INP": "ALTIPLANO_INP",
        "TASA": "ALTIPLANO_TASA",
        "DIRECTV": "ALTIPLANO_DTV",
        "METROTEL": "ALTIPLANO_METRO",
        "IPLAN": "ALTIPLANO_IPLAN",
        "ATC": "ALTIPLANO_ATC",
        "SION": "ALTIPLANO_SION",
    }.get(op, "")
    if env_prefix:
        host = os.environ.get(f"{env_prefix}_HOST", host).strip()
        port = os.environ.get(f"{env_prefix}_PORT", port).strip()
        base = os.environ.get(f"{env_prefix}_BASE_URL", base).strip()
    return host, port, base


def _int_env_positive_or_zero(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _int_env_at_least(name: str, default: int, min_value: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return max(min_value, default)
    try:
        return max(min_value, int(raw))
    except ValueError:
        return max(min_value, default)


def get_db_pool_bounds() -> tuple[int, int]:
    """Límites saneados para el pool de conexiones PostgreSQL."""
    pool_min = _int_env_at_least("DB_POOL_MIN", 2, 1)
    pool_max = _int_env_at_least("DB_POOL_MAX", 10, 1)
    if pool_max < pool_min:
        pool_max = pool_min
    return pool_min, pool_max


def get_dashboard_tree_cache_seconds_default() -> int:
    """TTL por defecto para árboles RAMA y OLT (Postgres). Default 1800 s."""
    return _int_env_positive_or_zero("DASHBOARD_TREE_CACHE_SECONDS", 1800)


def get_dashboard_rama_cache_seconds() -> int:
    """
    TTL del árbol dashboard RAMA. Si ``DASHBOARD_RAMA_CACHE_SECONDS`` está definido,
    tiene prioridad sobre ``DASHBOARD_TREE_CACHE_SECONDS``.
    """
    raw = os.environ.get("DASHBOARD_RAMA_CACHE_SECONDS", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return get_dashboard_tree_cache_seconds_default()


def get_dashboard_olt_cache_seconds() -> int:
    """
    TTL del árbol dashboard OLT. Si ``DASHBOARD_OLT_CACHE_SECONDS`` está definido,
    tiene prioridad sobre ``DASHBOARD_TREE_CACHE_SECONDS``.
    """
    raw = os.environ.get("DASHBOARD_OLT_CACHE_SECONDS", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return get_dashboard_tree_cache_seconds_default()


def get_dashboard_rama_power_cache_seconds() -> int:
    """
    TTL de resultados de `/dashboard/rama/consultar` (potencias por rama).
    Default bajo para reducir latencia percibida sin dejar datos viejos mucho tiempo.
    """
    raw = os.environ.get("DASHBOARD_RAMA_POWER_CACHE_SECONDS", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return _int_env_positive_or_zero("DASHBOARD_POWER_CACHE_SECONDS", 45)


def get_dashboard_calidad_cache_seconds() -> int:
    """
    TTL del resumen del dashboard de calidad de inventario.
    Si ``DASHBOARD_CALIDAD_CACHE_SECONDS`` está definido, tiene prioridad.
    """
    raw = os.environ.get("DASHBOARD_CALIDAD_CACHE_SECONDS", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return get_dashboard_tree_cache_seconds_default()


def get_altiplano_power_workers() -> int:
    """Cantidad máxima de workers para consultar potencias en paralelo."""
    return _int_env_at_least("ALTIPLANO_POWER_WORKERS", 8, 1)


class Config:
    """Configuración base de Flask y parámetros globales del proyecto."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-in-production")
    HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
    PORT = int(os.environ.get("FLASK_PORT", "9002"))
    DEBUG = os.environ.get("FLASK_DEBUG", "1").lower() in ("1", "true", "yes")
    DB_POOL_MIN, DB_POOL_MAX = get_db_pool_bounds()
    DB_CONNECT_TIMEOUT_SECS = _int_env_at_least("DB_CONNECT_TIMEOUT_SECS", 5, 1)
    DB_STATEMENT_TIMEOUT_MS = _int_env_positive_or_zero("DB_STATEMENT_TIMEOUT_MS", 30000)
    DB_IDLE_IN_TXN_TIMEOUT_MS = _int_env_positive_or_zero("DB_IDLE_IN_TXN_TIMEOUT_MS", 15000)
    DB_APP_NAME = (os.environ.get("DB_APP_NAME", "gpon-inventory").strip() or "gpon-inventory")
    # Ruta bajo `static/` para el logo del splash (índice). Ej.: img/SPLASH_LOGO.png
    SPLASH_LOGO_STATIC = (
        os.environ.get("SPLASH_LOGO_PATH", "img/SPLASH_LOGO.png").strip() or "img/SPLASH_LOGO.png"
    )
