# ATC GPON Inventory

Panel web en Flask para consultas de inventario GPON con datos de Postgres y operaciones específicas sobre Altiplano.
El foco del proyecto es búsqueda por AID/CTO/RAMA, dashboards operativos y exportación CSV.
Este README está orientado a onboarding rápido de desarrollo local.

Para despliegue/operación (producción, checklist, troubleshooting ampliado), ver `README_DEPLOY.md`.

## 1) Quick Start (5 minutos)

### Requisitos

- Python 3.11+
- Acceso de red a Postgres
- Variables de entorno configuradas (podés partir de `.env.example`)

### Instalación

```bash
pip install -r requirements.txt
```

### Ejecución local

```bash
python app.py
```

La app levanta con `FLASK_HOST` y `FLASK_PORT` (por defecto `0.0.0.0:9002`).

## 2) Variables de entorno esenciales

Usá **una** de estas dos formas para DB:

- `DATABASE_URL=postgresql://user:pass@host:5432/dbname`
- o `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

Variables clave de app:

- `SECRET_KEY`
- `FLASK_HOST`
- `FLASK_PORT`
- `FLASK_DEBUG`

Hardening DB recomendado (hasta ~10 concurrentes):

- `DB_POOL_MIN=2`
- `DB_POOL_MAX=10`
- `DB_CONNECT_TIMEOUT_SECS=5`
- `DB_STATEMENT_TIMEOUT_MS=30000`
- `DB_IDLE_IN_TXN_TIMEOUT_MS=15000`
- `DB_APP_NAME=gpon-inventory`

Variables útiles de caché dashboards:

- `DASHBOARD_TREE_CACHE_SECONDS` (default `120`)
- `DASHBOARD_RAMA_CACHE_SECONDS` (override RAMA)
- `DASHBOARD_OLT_CACHE_SECONDS` (override OLT)

Altiplano (solo si usás acciones/potencias relacionadas):

- `ALTIPLANO_USER`, `ALTIPLANO_PASSWORD`
- credenciales por operador (`ALTIPLANO_TASA_USER`, `ALTIPLANO_TASA_PASSWORD`, etc.)

## 3) Correr tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

## 4) Endpoints y pantallas principales

Pantallas:

- `/` (consulta principal por AID/CTO/RAMA/alias)
- `/dashboard/rama`
- `/dashboard/olt`
- `/dashboard/camino-optico`
- `/dashboard/altiplano`
- `/dashboard/potencias-historico`

APIs / acciones:

- `POST /potencias`
- `POST /sn/cambiar`
- `GET /export/csv`
- `POST /dashboard/rama/consultar`
- `POST /dashboard/olt/consultar`
- `POST /dashboard/cto/consultar`
- `GET /api/potencias-historico/<ratc>`
- `GET /dashboard/potencias-historico/export.csv`
- `POST /dashboard/altiplano/ont-connection`
- `POST /dashboard/camino-optico/consultar`
- `GET /health`
- `GET /health?db=1`

## 5) Estructura del repo (breve)

- `web/`: factory Flask y rutas HTTP
- `services/`: lógica de negocio (inventario, dashboards, exportaciones)
- `templates/`: vistas HTML
- `static/`: CSS y JS estáticos
- `config.py`: lectura de variables de entorno
- `db.py`: pool y cursores de Postgres
- `queries.py`: SQL reutilizable
- `altiplano.py`: cliente HTTP hacia Altiplano
- `tests/`: suite de pruebas

## 6) Troubleshooting rápido

- **No conecta DB**
  - Revisar `DATABASE_URL` o `DB_*`
  - Probar `GET /health?db=1`

- **Error 500 en histórico**
  - Revisar logs por `request_id` en respuestas de error
  - Validar `ratc` y rango (`7|15|30`)

- **No trae datos en histórico**
  - Verificar que la rama exista en inventario (`RATC`)
  - Verificar que haya muestras recientes en `altiplano.potencias`

- **Dashboards lentos**
  - Ajustar `DASHBOARD_*_CACHE_SECONDS`
  - Revisar latencia/plan de consultas en Postgres

## 7) Operación y despliegue

Para runbook completo de despliegue, checks post-deploy, variables detalladas y recomendaciones operativas:

- `README_DEPLOY.md`
