"""
Pool de conexiones PostgreSQL y context manager para cursores.
"""
import logging
from contextlib import contextmanager
from typing import Optional

from psycopg2 import InterfaceError, OperationalError
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
            Config.DB_POOL_MIN,
            Config.DB_POOL_MAX,
            connect_timeout=Config.DB_CONNECT_TIMEOUT_SECS,
            application_name=Config.DB_APP_NAME,
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
    conn = None
    released = False
    cur = None
    try:
        for _ in range(2):
            conn = pool.getconn()
            if not getattr(conn, "closed", 1):
                break
            logger.warning("Conexión cerrada detectada en pool; se descarta y reintenta")
            pool.putconn(conn, close=True)
            conn = None
        if conn is None:
            raise OperationalError("No hay conexiones utilizables en el pool")

        conn.autocommit = False
        cur = conn.cursor()
        cur.execute("SET search_path TO aux, public;")
        if Config.DB_STATEMENT_TIMEOUT_MS > 0:
            cur.execute(f"SET LOCAL statement_timeout = {int(Config.DB_STATEMENT_TIMEOUT_MS)};")
        if Config.DB_IDLE_IN_TXN_TIMEOUT_MS > 0:
            cur.execute(
                f"SET LOCAL idle_in_transaction_session_timeout = {int(Config.DB_IDLE_IN_TXN_TIMEOUT_MS)};"
            )
        yield cur
        conn.commit()
    except (OperationalError, InterfaceError):
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                pool.putconn(conn, close=True)
                released = True
            except Exception:
                logger.exception("No se pudo descartar conexión DB rota")
        logger.exception("Fallo de operación DB en db_cursor")
        raise
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cur is not None:
            cur.close()
        if conn is not None and not released:
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
