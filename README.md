# ATC GPON Inventory

Panel Flask para consultas de inventario GPON (Postgres + Altiplano). Código del proyecto en el directorio `gpon-inventory`.

Variables útiles: `FLASK_HOST`, `FLASK_PORT`, `FLASK_DEBUG`, `SECRET_KEY`, `DB_POOL_MIN`, `DB_POOL_MAX`.

## Hardening DB (recomendado)

Para un uso de hasta ~10 operadores concurrentes, usar como baseline:

- `DB_POOL_MIN=2`
- `DB_POOL_MAX=10`
- `DB_CONNECT_TIMEOUT_SECS=5`
- `DB_STATEMENT_TIMEOUT_MS=30000`
- `DB_IDLE_IN_TXN_TIMEOUT_MS=15000`
- `DB_APP_NAME=gpon-inventory`

### Caché de dashboards (Postgres)

Los árboles de **Dashboard RAMA** y **Dashboard OLT** (y los CSV que exportan la misma vista) usan una **caché en memoria con TTL** para no repetir las consultas pesadas a Postgres en cada request. El valor por defecto es **120 segundos**.

| Variable | Descripción |
| -------- | ----------- |
| `DASHBOARD_TREE_CACHE_SECONDS` | TTL en segundos para ambos dashboards (default `120`). |
| `DASHBOARD_RAMA_CACHE_SECONDS` | Si está definido, sobrescribe el TTL solo para el dashboard RAMA. |
| `DASHBOARD_OLT_CACHE_SECONDS` | Si está definido, sobrescribe el TTL solo para el dashboard OLT. |

No hay invalidación manual: los datos se renuevan al vencer el TTL. Con **Gunicorn uWSGI con varios workers**, cada proceso tiene su propia caché (no compartida entre workers).

Poné `DASHBOARD_TREE_CACHE_SECONDS=0` (o el override por dashboard) para desactivar caché y forzar lectura en cada request.

## Ejecución

```bash
pip install -r requirements.txt
python app.py
```

Producción (ejemplo):

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:9000 wsgi:app
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

## Estructura

- `web/` — factory Flask y rutas
- `services/` — lógica de negocio (inventario, dashboards, exportaciones)
- `config.py` — variables de entorno
- `db.py` — pool de conexiones PostgreSQL
- `queries.py` — SQL reutilizable
- `altiplano.py` — cliente API potencias

## Nuevo dashboard: Historico de Potencias

- URL UI: `/dashboard/potencias-historico`
- API JSON: `/api/potencias-historico/<RATC>`
- Export CSV: `/dashboard/potencias-historico/export.csv?ratc=<RATC>&days=<7|15|30>`
- Objetivo: visualizar tendencia de potencia Rx por ONT (ultimos 30 dias) para una rama `RATC`.
- Flujo: resolver `RATC` -> `OLT-B-P` y consultar `altiplano.potencias` para construir series temporales.
- Rango configurable en UI/API: `7d`, `15d`, `30d` (default `30d`).
