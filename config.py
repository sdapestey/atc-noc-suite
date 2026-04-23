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
    user = os.environ.get("ALTIPLANO_USER", "")
    password = os.environ.get("ALTIPLANO_PASSWORD", "")
    return user, password


def _int_env_positive_or_zero(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def get_dashboard_tree_cache_seconds_default() -> int:
    """TTL por defecto para árboles RAMA y OLT (Postgres). Default 120 s."""
    return _int_env_positive_or_zero("DASHBOARD_TREE_CACHE_SECONDS", 120)


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


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-in-production")
    HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
    PORT = int(os.environ.get("FLASK_PORT", "9002"))
    DEBUG = os.environ.get("FLASK_DEBUG", "1").lower() in ("1", "true", "yes")
    DB_POOL_MAX = int(os.environ.get("DB_POOL_MAX", "20"))
