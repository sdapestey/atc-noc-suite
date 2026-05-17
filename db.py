"""
Pool de conexiones PostgreSQL y context manager para cursores.
"""
import logging
import threading
import time
from contextlib import contextmanager
from psycopg2 import InterfaceError, OperationalError
from psycopg2.pool import ThreadedConnectionPool

from config import Config, get_db_params

logger = logging.getLogger(__name__)

_pool: ThreadedConnectionPool | None = None
_last_healthcheck_ok_monotonic = 0.0
_healthcheck_lock = threading.Lock()


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
    """Cursor con search_path; devuelve la conexión al pool al salir.

    Reintenta una vez ante fallos operativos de DB (conexión stale/rota).
    """
    pool = init_pool()
    for attempt in range(2):
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
            return
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
            if attempt == 0:
                logger.warning("Fallo de operación DB en db_cursor; reintentando una vez")
                continue
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


def ensure_db_connection_ready(max_age_seconds: int = 20) -> bool:
    """Verifica conectividad DB y recicla el pool si detecta estado roto.

    Para evitar sobrecarga en cada request, usa una ventana temporal (`max_age_seconds`)
    durante la cual considera válida la última verificación exitosa.
    """
    global _last_healthcheck_ok_monotonic
    now = time.monotonic()
    if now - _last_healthcheck_ok_monotonic <= max_age_seconds:
        return True

    with _healthcheck_lock:
        now = time.monotonic()
        if now - _last_healthcheck_ok_monotonic <= max_age_seconds:
            return True

        if healthcheck_db():
            _last_healthcheck_ok_monotonic = time.monotonic()
            return True

        logger.warning("Fallo de healthcheck DB; reciclando pool y reintentando una vez")
        close_pool()
        try:
            init_pool()
        except Exception:
            logger.exception("No se pudo recrear el pool de DB")
            return False

        if healthcheck_db():
            _last_healthcheck_ok_monotonic = time.monotonic()
            return True
        return False
