# Deploy Runbook (ATC GPON Inventory)

Guía breve para desplegar y operar la app sin tocar código.

## 1) Requisitos

- Python 3.11+
- Acceso de red a Postgres y endpoints Altiplano
- Variables de entorno configuradas (idealmente en `.env` fuera de repositorio)

## 2) Variables de entorno mínimas

### Flask / app

- `SECRET_KEY`
- `FLASK_HOST` (default: `0.0.0.0`)
- `FLASK_PORT` (default: `9000`)
- `FLASK_DEBUG` (`0` en producción)

### Base de datos

Usar **una** de estas opciones:

- `DATABASE_URL=postgresql://user:pass@host:5432/dbname`

o bien:

- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`

Parámetros de pool/timeouts recomendados (hasta ~10 concurrentes):

- `DB_POOL_MIN=2`
- `DB_POOL_MAX=10`
- `DB_CONNECT_TIMEOUT_SECS=5`
- `DB_STATEMENT_TIMEOUT_MS=30000`
- `DB_IDLE_IN_TXN_TIMEOUT_MS=15000`
- `DB_APP_NAME=gpon-inventory`

### Altiplano (según operador/entorno)

- Global fallback:
  - `ALTIPLANO_USER`
  - `ALTIPLANO_PASSWORD`
- Por operador (ejemplos):
  - `ALTIPLANO_TASA_USER` / `ALTIPLANO_TASA_PASSWORD`
  - `ALTIPLANO_DTV_USER` / `ALTIPLANO_DTV_PASSWORD`
  - `ALTIPLANO_IPLAN_USER` / `ALTIPLANO_IPLAN_PASSWORD`
  - `ALTIPLANO_METRO_USER` / `ALTIPLANO_METRO_PASSWORD`
  - `ALTIPLANO_SION_USER` / `ALTIPLANO_SION_PASSWORD`
  - `ALTIPLANO_ATC_USER` / `ALTIPLANO_ATC_PASSWORD`
  - `ALTIPLANO_INP_USER` / `ALTIPLANO_INP_PASSWORD`
- Endpoints NBI (si necesitás override de defaults):
  - `<PREFIJO>_HOST`, `<PREFIJO>_PORT`, `<PREFIJO>_BASE_URL`
  - Prefijos: `ALTIPLANO_TASA`, `ALTIPLANO_DTV`, `ALTIPLANO_IPLAN`,
    `ALTIPLANO_METRO`, `ALTIPLANO_SION`, `ALTIPLANO_ATC`, `ALTIPLANO_INP`

### Caché dashboards (opcional)

- `DASHBOARD_TREE_CACHE_SECONDS` (default: `1800`)
- `DASHBOARD_RAMA_CACHE_SECONDS` (override específico)
- `DASHBOARD_OLT_CACHE_SECONDS` (override específico)

## 3) Instalación

```bash
pip install -r requirements.txt
```

## 4) Ejecución

### Desarrollo

```bash
python app.py
```

### Producción (Gunicorn + wsgi)

```bash
gunicorn -w 4 -b 0.0.0.0:9000 wsgi:app
```

Notas:

- Ajustar `-w` según CPU/RAM.
- Ejecutar detrás de reverse proxy (Nginx/Traefik) para TLS y timeouts.

## 5) Healthchecks

- App viva:
  - `GET /health`
- App + conectividad DB:
  - `GET /health?db=1`

Esperado:

- HTTP 200 y `{"ok": true, ...}`

## 6) Checklist post-deploy

- [ ] `/health` responde OK
- [ ] `/health?db=1` responde OK
- [ ] Búsqueda por AID numérico funciona
- [ ] Búsqueda por `FATC` / `RATC` funciona
- [ ] Búsqueda por alias (`SRVC_LOC_*`, `RES_MT_*`, `RES_IP_*`) funciona
- [ ] Potencias TX/RX cargan en vistas principales
- [ ] Dashboard `/dashboard/potencias-historico` responde y grafica una rama RATC válida
- [ ] Selector de rango `7d/15d/30d` funciona en histórico
- [ ] Export CSV del histórico descarga datos según `RATC + rango`
- [ ] Altiplano INP crea `ont-connection` correctamente
- [ ] Export CSV funciona en índice y dashboards

## 7) Troubleshooting rápido

- **No conecta DB**
  - Verificar `DATABASE_URL` o `DB_*`
  - Probar conectividad de red/firewall al host/puerto de Postgres

- **Falla login/operación Altiplano**
  - Verificar credenciales por operador (`ALTIPLANO_*_USER/PASSWORD`)
  - Verificar `HOST/PORT/BASE_URL` del entorno NBI
  - Revisar reachability de red hacia Altiplano

- **Dashboards lentos**
  - Subir TTL de caché (`DASHBOARD_*_CACHE_SECONDS`)
  - Revisar latencia/plan de ejecución en Postgres

- **Resultados vacíos inesperados**
  - Confirmar formato de input (AID/FATC/RATC/alias)
  - Validar que haya datos en estado `IN SERVICE` en tablas fuente

- **Historico de potencias sin datos**
  - Verificar que la rama RATC exista en `cm.inventory_fat_occupation.path_atc`
  - Verificar mapeo a `aux.bajada_inventario.fibra_f01_f02_f03` y `object_name`
  - Verificar muestras recientes en `altiplano.potencias` (ultimos 30 dias)
