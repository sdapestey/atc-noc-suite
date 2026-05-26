# Deploy Runbook (ATC NOC Suite)

Guía breve para desplegar y operar la app sin tocar código.

## 1) Requisitos

- Python 3.11+ (instalación bare metal) **o** Docker + Docker Compose (recomendado en servidor)
- Acceso de red a Postgres y endpoints Altiplano
- Variables de entorno configuradas (idealmente en `.env` fuera de repositorio)

### ¿Qué son Gunicorn y Nginx?

| Componente | Rol |
|------------|-----|
| **Gunicorn** | Servidor de aplicación Python. Ejecuta varios **workers** (procesos) de tu app Flask para atender varios usuarios a la vez. Reemplaza `python app.py` en producción. |
| **Nginx** | **Reverse proxy** y servidor web delante de Gunicorn: recibe el HTTP en el puerto 80/443, sirve archivos estáticos (`/static/`) y reenvía el resto a Gunicorn. Aporta timeouts largos, TLS y un solo punto de entrada. |

En desarrollo suele alcanzar `python app.py` (un proceso). Con **8 operadores**, conviene Gunicorn con varios workers.

### Docker (servidor)

En Docker, **Gunicorn corre dentro de un único contenedor** (`noc-suite`) publicado en el puerto **9000**.

```bash
# En el servidor, con .env configurado (DB, Altiplano, SECRET_KEY, etc.)
docker compose up -d --build
# UI: http://<IP-del-servidor>:9000
```

Archivos: `Dockerfile`, `docker-compose.yml`.

**Red:** el contenedor debe llegar a Postgres (`DB_HOST`) y Altiplano en tu LAN. Si la DB está en el mismo host que Docker, probá `DB_HOST=host.docker.internal` (Linux con `extra_hosts: host-gateway` ya está en el compose) o la IP real del host, no `127.0.0.1` del contenedor.

```bash
docker compose exec noc-suite curl -fsS http://127.0.0.1:9000/health?db=1
docker compose logs -f noc-suite
```

Si antes levantaste el contenedor `atc-noc-suite-nginx` (stack antiguo con Nginx en Docker), eliminalo y volvé a levantar solo la app:

```bash
docker compose stop nginx 2>/dev/null; docker compose rm -f atc-noc-suite-nginx 2>/dev/null
docker compose up -d --build
```

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
- `DB_APP_NAME=atc-noc-suite`

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
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-prod.txt
pip install -r requirements-dev.txt   # solo en host de CI/desarrollo
```

`requirements-prod.txt` incluye `gunicorn` además de `requirements.txt`.

## 4) Ejecución

### Desarrollo

```bash
python app.py
```

Usar `FLASK_DEBUG=1` solo en local. No exponer `0.0.0.0` sin proxy en producción.

### Producción (~8 operadores): Gunicorn + Nginx

La app escucha en **loopback**; Nginx termina TLS y sirve `/static/` directo.

**1. Variables** (ver `.env.example`). Perfil sugerido 8 operadores:

- `FLASK_DEBUG=0`, `STATIC_CACHE_MAX_AGE=86400`
- `DB_POOL_MIN=2`, `DB_POOL_MAX=8` (con 4 workers Gunicorn → hasta ~32 conexiones pico; validar en Postgres)
- `DASHBOARD_TREE_CACHE_SECONDS=1800`
- `CONSULTA_POTENCIAS_BATCH_WORKERS=12`, `CONSULTA_POTENCIAS_PARALLEL_MAX=32`
- `ALTIPLANO_POWER_CTO_WORKERS=6`, `ALTIPLANO_POWER_WORKERS=16`

**2. Gunicorn** (desde la raíz del repo, con `.env` cargado por `config.py`):

```bash
gunicorn -c deploy/gunicorn.conf.py wsgi:app
```

Equivalente explícito:

```bash
gunicorn -w 4 -b 127.0.0.1:9000 --timeout 300 wsgi:app
```

Archivos de referencia en `deploy/`:

- `deploy/gunicorn.conf.py` — workers, timeout 300 s (consulta masiva)
- `deploy/nginx-atc-noc-suite.conf.example` — proxy + `proxy_read_timeout 300s` + `/static/`
- `deploy/atc-noc-suite.service.example` — unidad systemd

**3. systemd** (ejemplo):

```bash
sudo cp deploy/atc-noc-suite.service.example /etc/systemd/system/atc-noc-suite.service
# Editar User, WorkingDirectory, EnvironmentFile y ruta al venv
sudo systemctl daemon-reload
sudo systemctl enable --now atc-noc-suite
```

**4. Nginx**:

```bash
sudo cp deploy/nginx-atc-noc-suite.conf.example /etc/nginx/sites-available/atc-noc-suite
# Editar server_name, alias de /static/ y TLS
sudo ln -sf /etc/nginx/sites-available/atc-noc-suite /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

**5. Verificación**

```bash
curl -sS http://127.0.0.1:9000/health
curl -sS http://127.0.0.1:9000/health?db=1
```

Notas:

- **No** usar `python app.py` en producción (un solo proceso, sin timeouts de proxy).
- Ajustar `GUNICORN_WORKERS` (típico 4 en VM 4 vCPU / 8 GB RAM).
- Si Altiplano devuelve muchos HTTP 500, bajar workers de potencias en `.env` antes de subir CPU.

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
