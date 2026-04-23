"""
Pool de conexiones PostgreSQL y context manager para cursores.
"""
import logging
import os
from contextlib import contextmanager
from typing import Optional

from psycopg2.pool import ThreadedConnectionPool

from config import Config, get_db_params

logger = logging.getLogger(__name__)

_pool: Optional[ThreadedConnectionPool] = None


def init_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    params = get_db_params()
    if not params.get("password"):
        logger.warning(
            "DB_PASSWORD no definido: definí DATABASE_URL o DB_PASSWORD en el entorno / .env"
        )
    try:
        _pool = ThreadedConnectionPool(
            1,
            Config.DB_POOL_MAX,
            **params,
        )
    except Exception:
        logger.exception("No se pudo crear el pool de conexiones PostgreSQL")
        raise
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def db_cursor():
    """Cursor con search_path; devuelve la conexión al pool al salir."""
    pool = init_pool()
    conn = pool.getconn()
    cur = None
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute("SET search_path TO aux, public;")
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if cur is not None:
            cur.close()
        pool.putconn(conn)


def healthcheck_db() -> bool:
    """True si hay al menos una conexión usable."""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        logger.exception("healthcheck_db falló")
        return False
