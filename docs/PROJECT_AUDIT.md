# Auditoría técnica — ATC NOC Suite (2026-05)

Prioridad: no romper contratos API/UI para operadores. Suite de tests: `pytest tests/` (335 passed, 2026-05).

## 1. Mapa del proyecto

| Área | Rol |
|------|-----|
| `app.py` / `wsgi.py` | Entrada WSGI; instancia Flask vía `create_app()`. |
| `web/__init__.py` | Factory: carpetas `templates/` y `static/`, headers seguridad, `nav_tab` por path. |
| `web/routes.py` | Registro de rutas Flask (consulta `/`, dashboards, export, APIs JSON, potencias async). |
| `services/` | Lógica de dominio: inventario, camino óptico/GIS, histórico potencias, cache, exports, calidad inventario, etc. |
| `templates/` | Jinja: dashboards por página + `partials/` (`noc_head`, nav, splash). |
| `static/css/` | `devops-dashboard.css` (base + muchas páginas), `noc-tools.css`, `rama-cto-map.css`, `splash.css`. |
| `static/js/` | Por dashboard + `noc-tools.js`, mapas Leaflet, splash, theme. |
| `altiplano.py`, `db.py`, `queries.py`, `config.py` | Integración Altiplano, pool DB, SQL, configuración. |
| `tests/` | pytest con `conftest` y cliente Flask. |

**Nota Windows/Git:** A veces el índice muestra la misma ruta con `/` y `\`; no implica dos copias físicas de `routes.py` si solo existe un archivo bajo `web/`.

## 2. Hallazgos priorizados

### Crítico
- Ninguno bloqueante detectado en esta pasada: rutas coherentes, factory única, tests verdes.

### Medio
- **Superficie CSS:** `devops-dashboard.css` sigue siendo grande; histórico potencias ya está en `static/css/dashboard-historico-potencias.css`. Resto de páginas: extraer por fases.
- **Duplicación de patrones mapa:** Leaflet + `rama-cto-map.css` repetidos en `index.html`, `dashboard_rama.html`, `dashboard_camino_optico.html` — candidato a partial Jinja o include de bloque `<head>` solo donde haga falta.
- **Estados vacíos:** Clase `empty-state-note` + `muted` ya unifica mensajes; algún panel aún mezcla `style="display:…"` inline con reglas CSS (revisado en histórico potencias en esta iteración).

### Bajo
- **Artefactos locales:** `resultado.csv` / `resultado.cs` como salidas puntuales — añadidos a `.gitignore` en esta iteración.
- **Comentarios tipo TODO en UI:** comentario `/* COPIAR TODO */` en `index.html` (copiar resultados) no es deuda técnica, puede confundir en búsquedas; renombrar comentario opcional.

## 3. Cambios realizados en esta iteración (diff enfocado)

| Cambio | Motivo |
|--------|--------|
| `templates/dashboard_potencias_historico.html` | Quitar `style="display:block"` en `#no-data`; al mostrar el mensaje el JS usa `display = ""` para respetar `.page-historico-potencias #no-data { display: flex; … }` ya definido en `devops-dashboard.css`. |
| `.gitignore` | Ignorar `resultado.csv` y `resultado.cs` para no versionar salidas locales. |

**No eliminado** (sin evidencia total de no uso): endpoints, servicios completos, plantillas no referenciadas — requieren trazabilidad por dominio.

## 4. Herramientas ejecutadas

```text
python -m pytest tests/ -q --tb=no
# → 269 passed (antes de cambios puntuales en histórico)

python -m pytest tests/test_dashboard_potencias_historico.py -q --tb=short
# → 13 passed (tras ajuste #no-data)

python -m ruff check web services altiplano.py db.py queries.py config.py
# → sin hallazgos en esta configuración
```

## 5. Deuda técnica / siguientes pasos (1–3)

1. **Unificación UI por fases:** definir checklist (botones `.btn` / `.btn-ghost`, cards `.card`, espaciado `--space-*`) y migrar una pantalla por PR con captura antes/después.
2. **Leaflet head partial:** `templates/partials/head_leaflet.html` (índice, RAMA, camino óptico; flag `leaflet_rama_map_css`).
3. **Histórico potencias:** JS en `static/js/dashboard-potencias-historico.js`; CSS en `dashboard-historico-potencias.css`; Chart.js vía `partials/head_chartjs.html` al pie del body.
4. **Código muerto:** ejecutar búsqueda dirigida por módulo (p. ej. `services/exports.py` vs rutas de export) y anotar candidatos; usar `vulture` solo como pista, confirmar con grep + tests antes de borrar.
