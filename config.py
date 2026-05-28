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


def get_altiplano_inp_intent_restconf_paths() -> list[str]:
    """
    Rutas RESTCONF relativas a ``.../rest/restconf/data/`` para listar intents en INP.

    Prioridad: ``ALTIPLANO_INP_INTENT_DATA_PATHS`` (coma-separado; definido por release/NBI),
    luego valores habituales. Si el AC devuelve *Module ibn does not exist*, probá sin
    ``altiplano-target`` (ya alternamos en código) o consultá el Northbound Guide para la
    ruta exacta de tu versión y configurá la variable de entorno.
    """
    raw = os.environ.get("ALTIPLANO_INP_INTENT_DATA_PATHS", "").strip()
    paths: list[str] = []
    if raw:
        paths.extend(p.strip() for p in raw.split(",") if p.strip())
    paths.extend(
        (
            "ibn:intent",
            "ibn:ibn/intent",
            "ibn:ibn",
        )
    )
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def get_altiplano_tasa_intent_restconf_paths() -> list[str]:
    """
    Rutas RESTCONF relativas a ``.../rest/restconf/data/`` para listar intents en TASA.

    Override: ``ALTIPLANO_TASA_INTENT_DATA_PATHS`` (coma-separado).
    """
    raw = os.environ.get("ALTIPLANO_TASA_INTENT_DATA_PATHS", "").strip()
    paths: list[str] = []
    if raw:
        paths.extend(p.strip() for p in raw.split(",") if p.strip())
    paths.extend(
        (
            "ibn:ibn",
            "ibn:ibn/intent",
            "ibn:intent",
        )
    )
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def get_altiplano_tasa_discovery_search_timeout_s() -> int:
    """Timeout por POST ``ibn:search-intents`` al detectar SVLAN en borrado TASA (default 20 s)."""
    return _int_env_at_least("ALTIPLANO_TASA_DISCOVERY_SEARCH_TIMEOUT_S", 20, 5)


def get_altiplano_tasa_discovery_wide_list_enabled() -> bool:
    """
    Si True, tras ``search-intents`` intenta un GET acotado del árbol IBN (lento en muchos AC).

    Default **False** — el listado global ``ibn:ibn`` suele tardar minutos y bloquea el borrado.
    Variable: ``ALTIPLANO_TASA_DISCOVERY_WIDE_LIST`` = ``1`` / ``true`` / ``yes``.
    """
    raw = os.environ.get("ALTIPLANO_TASA_DISCOVERY_WIDE_LIST", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_altiplano_tasa_discovery_wide_list_timeout_s() -> int:
    """Timeout del GET opcional de listado IBN en discovery TASA (default 12 s)."""
    return _int_env_at_least("ALTIPLANO_TASA_DISCOVERY_WIDE_LIST_TIMEOUT_S", 12, 5)


def get_altiplano_inp_search_http_timeout_s() -> int:
    """
    Timeout en segundos para cada GET RESTCONF de **búsqueda** de intents INP (Orquestador).

    Los listados ``ibn:ibn`` / ``ibn:intent`` pueden tardar bastante en AC lentos o redes congestionadas.
    Variable de entorno: ``ALTIPLANO_INP_SEARCH_HTTP_TIMEOUT_S`` (default **75**, mínimo **15**).
    """
    return _int_env_at_least("ALTIPLANO_INP_SEARCH_HTTP_TIMEOUT_S", 75, 15)


def get_altiplano_inp_wide_search_http_timeout_s() -> int:
    """
    Timeout en segundos para el GET RESTCONF del **listado global** de intents cuando la
    consulta INP es solo Access ID (sin device/target): el árbol ``ibn:ibn`` / ``ibn:intent``
    puede tardar bastante más que un GET por instancia.

    Variable: ``ALTIPLANO_INP_WIDE_SEARCH_HTTP_TIMEOUT_S`` (default **300**, mínimo **75**).
    """
    return _int_env_at_least("ALTIPLANO_INP_WIDE_SEARCH_HTTP_TIMEOUT_S", 300, 75)


def get_altiplano_inp_intent_probe_http_timeout_s() -> int:
    """
    Timeout por GET para **sondas** de alineación (``content=all``, leafs RESTCONF, ``ibn/yang/…``).

    La consulta INP encadena muchas peticiones opcionales; si comparten el timeout largo de
    búsqueda, un AC lento puede dejar la UI minutos en «Consultando…». Variable de entorno:
    ``ALTIPLANO_INP_INTENT_PROBE_HTTP_TIMEOUT_S`` (default **15**, mínimo **5**).
    """
    return _int_env_at_least("ALTIPLANO_INP_INTENT_PROBE_HTTP_TIMEOUT_S", 15, 5)


def get_altiplano_inp_intent_metadata_yang_version() -> str:
    """
    Segmento de versión YANG en la URL de metadata IBN que usa la GUI Altiplano, p. ej.::

        .../rest/ibn/yang/metadata/ont-connection/11/data/ont-connection:ont-connection-state

    Default **11**. Override: ``ALTIPLANO_INP_INTENT_METADATA_YANG_VERSION``.
    """
    raw = os.environ.get("ALTIPLANO_INP_INTENT_METADATA_YANG_VERSION", "").strip()
    return raw if raw else "11"


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


def get_dashboard_historico_cache_seconds() -> int:
    """TTL de ``GET /api/potencias-historico`` (consulta Postgres, sin Altiplano)."""
    return _int_env_positive_or_zero("DASHBOARD_HISTORICO_CACHE_SECONDS", 600)


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


def get_inventario_estadisticas_cache_seconds() -> int:
    """TTL de estadísticas altas/bajas (consultas pesadas). Default 1 h."""
    raw = os.environ.get("INVENTARIO_ESTADISTICAS_CACHE_SECONDS", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return 3600


def get_altiplano_token_cache_max_age_seconds() -> int:
    """
    Edad máxima del token Altiplano cacheado antes de forzar nuevo login.
    ``0`` desactiva la caducidad por tiempo (solo se renueva por 401/403 o force_refresh).
    Default 3300 s (~55 min) para anticipar típicos JWT de ~1 h.
    """
    return _int_env_positive_or_zero("ALTIPLANO_TOKEN_CACHE_MAX_AGE_SECONDS", 3300)


def get_consulta_altiplano_ui_cache_seconds() -> int:
    """
    TTL de la sesión Altiplano en el navegador (consulta índice: bajar PON, cambiar SN).
    Se guarda en ``sessionStorage`` tras validar usuario/contraseña contra el NBI.
    Default 1800 s (30 min); mínimo 60 s.
    """
    return _int_env_at_least("CONSULTA_ALTIPLANO_UI_CACHE_SECONDS", 1800, 60)


def get_consulta_potencias_parallel_max() -> int:
    """RAMAs/CTOs en paralelo en consulta masiva (fallback sin /potencias/batch)."""
    return _int_env_at_least("CONSULTA_POTENCIAS_PARALLEL_MAX", 48, 1)


def get_consulta_potencias_batch_workers() -> int:
    """RAMAs/CTOs en paralelo dentro de ``POST /potencias/batch``."""
    return _int_env_at_least("CONSULTA_POTENCIAS_BATCH_WORKERS", 4, 1)


def get_consulta_potencias_preload_batch_workers() -> int:
    """Lotes ``/potencias/batch`` simultáneos en precarga masiva (navegador)."""
    return _int_env_at_least("CONSULTA_POTENCIAS_PRELOAD_BATCH_WORKERS", 1, 1)


def get_altiplano_power_cto_workers(*, carga_masiva: bool = False) -> int:
    """CTOs en paralelo al consultar una RAMA (cada CTO sigue paralelizando ONTs)."""
    if carga_masiva:
        return _int_env_at_least("ALTIPLANO_POWER_CTO_WORKERS_MASIVO", 2, 1)
    return _int_env_at_least("ALTIPLANO_POWER_CTO_WORKERS", 8, 1)


def get_altiplano_power_workers(*, carga_masiva: bool = False) -> int:
    """ONT en paralelo por CTO contra Altiplano."""
    if carga_masiva:
        return _int_env_at_least("ALTIPLANO_POWER_WORKERS_MASIVO", 8, 1)
    return _int_env_at_least("ALTIPLANO_POWER_WORKERS", 24, 1)


def get_noc_wiki_url() -> str:
    """URL del wiki NOC (pestaña externa en la barra de dashboards)."""
    default = "http://10.90.1.196:6875/"
    raw = os.environ.get("NOC_WIKI_URL", default).strip()
    return raw or default


def get_ftth_toolbox_config() -> dict[str, str]:
    """Credenciales y URL base para Web ToolBox FTTH Norte (cambio de CTO vía SendFTTH)."""
    base = os.environ.get(
        "FTTH_TOOLBOX_BASE_URL", "https://ar-toolbox.simpledatacorp.com"
    ).strip().rstrip("/")
    user = os.environ.get("FTTH_TOOLBOX_USER", "").strip()
    password = os.environ.get("FTTH_TOOLBOX_PASSWORD", "").strip()
    ally_atc = os.environ.get("FTTH_TOOLBOX_ALLY_ATC_ID", "8").strip() or "8"
    return {
        "base_url": base,
        "user": user,
        "password": password,
        "ally_atc_id": ally_atc,
    }


class Config:
    """Configuración base de Flask y parámetros globales del proyecto."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-in-production")
    HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
    PORT = int(os.environ.get("FLASK_PORT", "9002"))
    DEBUG = os.environ.get("FLASK_DEBUG", "1").lower() in ("1", "true", "yes")
    # Caché navegador para /static/ (segundos). En DEBUG suele ser 0.
    STATIC_CACHE_MAX_AGE = int(os.environ.get("STATIC_CACHE_MAX_AGE", "0" if DEBUG else "86400"))
    DB_POOL_MIN, DB_POOL_MAX = get_db_pool_bounds()
    DB_CONNECT_TIMEOUT_SECS = _int_env_at_least("DB_CONNECT_TIMEOUT_SECS", 5, 1)
    DB_STATEMENT_TIMEOUT_MS = _int_env_positive_or_zero("DB_STATEMENT_TIMEOUT_MS", 30000)
    DB_IDLE_IN_TXN_TIMEOUT_MS = _int_env_positive_or_zero("DB_IDLE_IN_TXN_TIMEOUT_MS", 15000)
    DB_APP_NAME = (os.environ.get("DB_APP_NAME", "atc-noc-suite").strip() or "atc-noc-suite")
    # Ruta bajo `static/` para el logo del splash (índice): pictograma sin texto (PNG RGBA por defecto).
    SPLASH_LOGO_STATIC = (
        os.environ.get("SPLASH_LOGO_PATH", "img/splash-mark.png").strip() or "img/splash-mark.png"
    )
