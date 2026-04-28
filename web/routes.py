"""Registro de rutas HTTP de la aplicación Flask.

Este módulo concentra la capa web: parsea requests, valida entradas,
invoca servicios y devuelve templates o JSON según corresponda.
"""
from datetime import datetime, timezone
import re
from uuid import uuid4

from flask import Response, current_app, g, jsonify, redirect, render_template, request, url_for
from urllib.parse import quote_plus

from db import ensure_db_connection_ready, healthcheck_db
from services.domain import split_index_query_tokens
from services import (
    ALLOWED_HISTORICO_DAYS,
    cambiar_sn_ont,
    consultar_access_id_desde_alias,
    consultar_access_id_baja_o_ausente,
    consultar_access_id_detalle_desde_bajada_inventario,
    consultar_access_id_potencias,
    consultar_cto_coordenadas,
    consultar_cto_estructura,
    consultar_cto_potencias,
    consultar_dashboard_rama,
    inventario_dashboard_rama,
    consultar_rama_estructura,
    consultar_rama_potencias,
    dashboard_camino_optico_access_id,
    dashboard_camino_optico_cto,
    dashboard_camino_optico_rama,
    dashboard_calidad_inventario_hallazgos,
    dashboard_calidad_inventario_resumen,
    dashboard_olts,
    dashboard_ramas,
    crear_ont_connection_intent,
    estructura_dashboard_lt,
    export_dashboard_olts_csv,
    export_dashboard_ramas_csv,
    export_csv_potencias_historico_rama,
    export_dashboard_calidad_inventario_csv,
    export_index_query_csv,
    consultar_potencias_altiplano_ahora_rama,
    consultar_potencias_historico_rama,
)


def _build_google_maps_search_url(lat: float, lon: float) -> str:
    """Construye una URL de Google Maps a partir de lat/lon."""
    lat_lon = f"{lat},{lon}"
    return "https://www.google.com/maps/search/?api=1&query=" f"{quote_plus(lat_lon)}"


def _update_route_and_maps_from_result(resultado: dict, ruta: dict) -> str | None:
    """Actualiza `ruta` (AID/CTO/RAMA) desde un resultado y devuelve URL de Maps.

    Args:
        resultado: Dict con claves compatibles con el detalle de Access ID.
        ruta: Estructura mutable usada por el template (`aid`, `cto`, `rama`).

    Returns:
        URL de Google Maps para la CTO si hay coordenadas; de lo contrario, `None`.
    """
    ruta["aid"] = resultado["AID"]
    ruta["cto"] = resultado["CTO"]
    ruta["rama"] = resultado.get("RAMA")
    if not resultado.get("CTO") or resultado["CTO"] == "—":
        return None
    coords = consultar_cto_coordenadas(resultado["CTO"])
    if not coords:
        return None
    return _build_google_maps_search_url(coords["lat"], coords["lon"])


def _is_alias_identifier(value_upper: str) -> bool:
    """Indica si el valor de búsqueda tiene formato alias soportado."""
    return (
        value_upper.startswith("SRVC_LOC_")
        or value_upper.startswith("RES_MT_")
        or value_upper.startswith("RES_IP_")
    )


def _resolve_index_consulta(token: str) -> dict:
    """Resuelve un token de búsqueda del índice (AID, CTO FATC, RAMA RATC o alias)."""
    token = (token or "").strip()
    vu = token.upper()
    consulta = {
        "token": token,
        "resultado": None,
        "tabla_cto": None,
        "es_rama": False,
        "ruta": {"aid": None, "cto": None, "rama": None},
        "cto_maps_url": None,
        "busqueda_aid": None,
    }
    if not token:
        return consulta

    if token.isdigit():
        resultado = consultar_access_id_detalle_desde_bajada_inventario(token)
        if resultado:
            consulta["resultado"] = resultado
            consulta["cto_maps_url"] = _update_route_and_maps_from_result(resultado, consulta["ruta"])
        else:
            consulta["busqueda_aid"] = consultar_access_id_baja_o_ausente(token)

    elif "FATC" in vu:
        consulta["tabla_cto"] = consultar_cto_estructura(token)
        consulta["ruta"]["cto"] = token
        coords = consultar_cto_coordenadas(token)
        if coords:
            lat_lon = f"{coords['lat']},{coords['lon']}"
            consulta["cto_maps_url"] = (
                "https://www.google.com/maps/search/?api=1&query="
                f"{quote_plus(lat_lon)}"
            )

    elif "RATC" in vu:
        consulta["tabla_cto"] = consultar_rama_estructura(token)
        consulta["es_rama"] = True
        consulta["ruta"]["rama"] = token

    elif _is_alias_identifier(vu):
        resultado = consultar_access_id_desde_alias(token)
        if resultado:
            consulta["resultado"] = resultado
            consulta["cto_maps_url"] = _update_route_and_maps_from_result(resultado, consulta["ruta"])
        else:
            consulta["busqueda_aid"] = {"tipo": "no_existe", "AID": token}

    return consulta


def _consulta_fila_count(c: dict) -> int:
    """Filas con equipos (detalle=1, tabla CTO/RAMA=suma de ONT)."""
    if c.get("resultado"):
        return 1
    t = c.get("tabla_cto")
    if not t:
        return 0
    if c.get("es_rama"):
        return sum(len(rows) for rows in t.values())
    return len(t) if isinstance(t, list) else 0


def _consulta_operadores_union(consultas: list[dict]) -> list[str]:
    """Unión de operadores con orden estable (para un solo toolbar con varias consultas)."""
    seen: set[str] = set()
    out: list[str] = []
    for q in consultas:
        t = q.get("tabla_cto")
        if not t or q.get("resultado"):
            continue
        if q.get("es_rama"):
            for rows in t.values():
                for r in rows:
                    op = (r or {}).get("OPERADOR")
                    if op and op not in seen:
                        seen.add(op)
                        out.append(op)
        else:
            for r in t:
                op = (r or {}).get("OPERADOR")
                if op and op not in seen:
                    seen.add(op)
                    out.append(op)
    return out


def _request_context_for_log() -> dict:
    return {
        "request_id": getattr(g, "request_id", "-"),
        "path": request.path,
        "method": request.method,
    }


def _log_and_internal_error(message: str):
    current_app.logger.exception(message, extra={"context": _request_context_for_log()})
    return jsonify({"error": message, "request_id": getattr(g, "request_id", "-")}), 500


def _csv_download_response(csv_text: str, filename: str) -> Response:
    """Respuesta HTTP para descargar CSV UTF-8 con BOM."""
    return Response(
        "\ufeff" + (csv_text or ""),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def register(app):
    """Registra todas las rutas HTTP en la app Flask.

    Además define constantes de negocio acotadas al contexto web
    (por ejemplo, valores fijos para intents de Altiplano).
    """
    ONT_CONNECTION_PIR_FIXED = 1000
    ONT_CONNECTION_CIR_FIXED = 35

    @app.before_request
    def attach_request_id():
        g.request_id = request.headers.get("X-Request-Id", "").strip() or str(uuid4())[:12]

    @app.before_request
    def ensure_db_ready():
        # Evita checks en assets/health y durante tests; en runtime previene 500 por conexión stale.
        if current_app.config.get("TESTING"):
            return None
        if request.path.startswith("/static/") or request.path == "/health":
            return None

        if ensure_db_connection_ready():
            return None

        message = "Base de datos no disponible temporalmente. Reintentá en unos segundos."
        is_json = (
            request.path.startswith("/api/")
            or request.path.endswith("/consultar")
            or request.path.endswith(".json")
            or request.accept_mimetypes.best == "application/json"
        )
        if is_json:
            return jsonify({"error": message, "request_id": getattr(g, "request_id", "-")}), 503
        return message, 503

    @app.route("/health")
    def health():
        payload = {"ok": True, "time": datetime.now(timezone.utc).isoformat()}
        if request.args.get("db"):
            payload["db"] = healthcheck_db()
            payload["ok"] = payload["db"]
        return jsonify(payload)

    @app.route("/dashboard")
    def dashboard_entry():
        tab = request.args.get("tab", "id").lower()
        if tab == "rama":
            return redirect(url_for("dash_rama"))
        if tab == "lt":
            return redirect(url_for("dash_olt"))
        if tab in ("camino", "camino-optico", "optico"):
            return redirect(url_for("dash_camino_optico"))
        if tab == "altiplano":
            return redirect(url_for("dash_altiplano"))
        if tab in ("historico", "potencias-historico"):
            return redirect(url_for("dash_potencias_historico"))
        if tab in ("calidad", "calidad-inventario"):
            return redirect(url_for("dash_calidad_inventario"))
        return redirect(url_for("index"))

    @app.route("/", methods=["GET", "POST"])
    def index():
        value = ""
        consultas = []

        if request.method == "POST":
            value = request.form.get("value", "").strip()
            for token in split_index_query_tokens(value):
                consultas.append(_resolve_index_consulta(token))

        if len(consultas) > 1:
            consulta_ops_merged = _consulta_operadores_union(consultas)
            consulta_row_counts = [_consulta_fila_count(c) for c in consultas]
        else:
            consulta_ops_merged = None
            consulta_row_counts = None

        return render_template(
            "index.html",
            consultas=consultas,
            value=value,
            consulta_ops_merged=consulta_ops_merged,
            consulta_row_counts=consulta_row_counts,
        )

    @app.route("/potencias", methods=["POST"])
    def potencias_async():
        """Endpoint AJAX de potencias para índice/rama/cto.

        Acepta un valor libre y decide automáticamente si consultar por:
        - Access ID (numérico)
        - CTO (FATC)
        - RAMA (RATC)
        """
        valor = (request.form.get("value") or "").strip()
        if not valor:
            return jsonify({"error": "Parámetro value requerido"}), 400
        valor_upper = valor.upper()

        if valor.isdigit():
            return jsonify(consultar_access_id_potencias(valor))

        if "FATC" in valor_upper:
            return jsonify(consultar_cto_potencias(valor))

        if "RATC" in valor_upper:
            return jsonify(consultar_rama_potencias(valor))

        if _is_alias_identifier(valor_upper):
            resolved = consultar_access_id_desde_alias(valor)
            if not resolved:
                return jsonify([])
            return jsonify(consultar_access_id_potencias(str(resolved.get("AID") or valor)))

        return jsonify([])

    @app.route("/sn/cambiar", methods=["POST"])
    def cambiar_sn():
        data = request.get_json(silent=True) or request.form
        access_id = (data.get("access_id") or "").strip()
        operador = (data.get("operador") or "").strip()
        ont_target = (data.get("ont_target") or "").strip()
        new_sn = (data.get("new_sn") or "").strip()

        if not access_id:
            return jsonify({"ok": False, "message": "access_id requerido"}), 400
        if not ont_target:
            return jsonify({"ok": False, "message": "ont_target requerido"}), 400
        if not new_sn:
            return jsonify({"ok": False, "message": "new_sn requerido"}), 400

        if len(new_sn) < 6 or len(new_sn) > 32:
            return jsonify({"ok": False, "message": "SN inválido (largo fuera de rango)"}), 400

        result = cambiar_sn_ont(
            access_id=access_id,
            operador=operador,
            ont_target=ont_target,
            new_sn=new_sn,
        )
        code = 200 if result.get("ok") else 502
        return jsonify(result), code

    @app.route("/export/csv")
    def export_index_csv():
        value = request.args.get("value", "").strip()
        data = export_index_query_csv(value)
        return _csv_download_response(data, "consulta.csv")

    @app.route("/dashboard/rama")
    def dash_rama():
        ramas = dashboard_ramas()
        return render_template("dashboard_rama.html", ramas=ramas)

    @app.route("/dashboard/rama/consultar", methods=["POST"])
    def dash_rama_consultar():
        rama = (request.form.get("rama") or "").strip()
        if not rama:
            return jsonify({"error": "Parámetro rama requerido"}), 400
        data = consultar_dashboard_rama(rama)
        return jsonify(data)

    @app.route("/dashboard/rama/inventario", methods=["POST"])
    def dash_rama_inventario():
        rama = (request.form.get("rama") or "").strip()
        if not rama:
            return jsonify({"error": "Parámetro rama requerido"}), 400
        data = inventario_dashboard_rama(rama)
        return jsonify(data)

    @app.route("/dashboard/rama/export.csv")
    def export_rama_csv():
        data = export_dashboard_ramas_csv()
        return _csv_download_response(data, "dashboard_ramas.csv")

    @app.route("/dashboard/olt")
    def dash_olt():
        olts = dashboard_olts()
        return render_template("dashboard_olt.html", olts=olts)

    @app.route("/dashboard/olt/consultar", methods=["POST"])
    def dash_olt_consultar():
        lt = request.form.get("lt", "").strip()
        return jsonify(estructura_dashboard_lt(lt))

    @app.route("/dashboard/olt/export.csv")
    def export_olt_csv():
        data = export_dashboard_olts_csv()
        return _csv_download_response(data, "dashboard_olts.csv")

    @app.route("/dashboard/cto/consultar", methods=["POST"])
    def dash_cto_consultar():
        cto = (request.form.get("cto") or "").strip()
        if not cto:
            return jsonify({"error": "Parámetro cto requerido"}), 400
        return jsonify(consultar_cto_potencias(cto))

    @app.route("/dashboard/camino-optico")
    def dash_camino_optico():
        return render_template("dashboard_camino_optico.html")

    @app.route("/dashboard/altiplano")
    def dash_altiplano():
        return render_template("dashboard_altiplano.html")

    @app.route("/dashboard/potencias-historico")
    def dash_potencias_historico():
        return render_template("dashboard_potencias_historico.html")

    @app.route("/dashboard/calidad-inventario")
    def dash_calidad_inventario():
        return render_template("dashboard_calidad_inventario.html")

    @app.route("/dashboard/calidad-inventario/resumen.json")
    def dash_calidad_inventario_resumen_json():
        try:
            payload = dashboard_calidad_inventario_resumen()
        except Exception:
            return _log_and_internal_error("Error interno consultando resumen de calidad")
        return jsonify(payload)

    @app.route("/dashboard/calidad-inventario/hallazgos.json")
    def dash_calidad_inventario_hallazgos_json():
        regla = (request.args.get("regla") or "").strip()
        operador = (request.args.get("operador") or "").strip()
        q = (request.args.get("q") or "").strip()
        limit = request.args.get("limit", default=500, type=int)
        try:
            payload = dashboard_calidad_inventario_hallazgos(
                regla=regla,
                operador=operador,
                q=q,
                limit=limit,
            )
        except Exception:
            return _log_and_internal_error("Error interno consultando hallazgos de calidad")
        return jsonify(payload)

    @app.route("/dashboard/calidad-inventario/export.csv")
    def dash_calidad_inventario_export_csv():
        regla = (request.args.get("regla") or "").strip()
        operador = (request.args.get("operador") or "").strip()
        q = (request.args.get("q") or "").strip()
        try:
            csv_text = export_dashboard_calidad_inventario_csv(
                regla=regla,
                operador=operador,
                q=q,
            )
        except Exception:
            return _log_and_internal_error("Error interno exportando hallazgos de calidad")
        return _csv_download_response(csv_text, "dashboard_calidad_inventario.csv")

    @app.route("/api/potencias-historico/<ratc>")
    def api_potencias_historico(ratc):
        days = request.args.get("days", default=30, type=int)
        try:
            payload = consultar_potencias_historico_rama(ratc, days=days)
        except Exception:
            return _log_and_internal_error("Error interno consultando historico de potencias")
        if not payload.get("ok"):
            return jsonify({"error": payload.get("error", "Error de consulta")}), int(
                payload.get("status_code", 500)
            )
        return jsonify(payload)

    @app.route("/api/potencias-historico/<ratc>/consultar-ahora", methods=["POST"])
    def api_potencias_historico_consultar_ahora(ratc):
        try:
            payload = consultar_potencias_altiplano_ahora_rama(ratc)
        except Exception:
            return _log_and_internal_error("Error interno consultando Altiplano (tiempo real)")
        if not payload.get("ok"):
            return jsonify({"error": payload.get("error", "Error de consulta")}), int(
                payload.get("status_code", 400)
            )
        return jsonify(payload)

    @app.route("/dashboard/potencias-historico/export.csv")
    def export_potencias_historico_csv():
        ratc = (request.args.get("ratc") or "").strip()
        days = request.args.get("days", default=30, type=int)
        if days not in ALLOWED_HISTORICO_DAYS:
            return jsonify({"error": "Parámetro days inválido. Valores permitidos: 1 (24h), 7, 15, 30"}), 400
        try:
            payload = export_csv_potencias_historico_rama(ratc, days=days)
        except Exception:
            return _log_and_internal_error("Error interno exportando historico de potencias")
        if not payload.get("ok"):
            return jsonify({"error": payload.get("error", "Error de consulta")}), int(
                payload.get("status_code", 500)
            )
        ratc_safe = re.sub(r"[^A-Za-z0-9._-]+", "_", ratc or "rama").strip("_") or "rama"
        ts_tag = datetime.now().strftime("%Y%m%d_%H%M")
        range_tag = "24h" if days == 1 else f"{days}d"
        filename = f"potencias_historico_{ratc_safe}_{range_tag}_{ts_tag}.csv"
        return _csv_download_response(payload["csv"], filename)


    @app.route("/dashboard/altiplano/ont-connection", methods=["POST"])
    def dash_altiplano_ont_connection():
        """Crea un intent ONT Connection desde la UI de Altiplano.

        Reglas importantes:
        - `device_name` y `fiber_name` se derivan server-side.
        - PIR/CIR siempre se fuerzan con constantes internas.
        """
        data = request.get_json(silent=True) or request.form
        operador = (data.get("operador") or "").strip()
        entorno_nbi = (data.get("entorno_nbi") or "").strip()
        sitio = (data.get("sitio") or "").strip()
        device_name = (data.get("device_name") or "").strip()
        lt = (data.get("lt") or "").strip()
        pon = (data.get("pon") or "").strip()
        ont = (data.get("ont") or "").strip()
        vno = (data.get("vno") or "").strip()
        fiber_name = (data.get("fiber_name") or "").strip()
        access_id = (data.get("access_id") or "").strip()
        if sitio:
            device_name = f"BA_OLTA_{sitio}"
        if device_name and lt and pon:
            fiber_name = f"{device_name}-{lt}-{pon}"

        required = {
            "operador": operador,
            "sitio": sitio,
            "device_name": device_name,
            "lt": lt,
            "pon": pon,
            "ont": ont,
            "vno": vno,
            "fiber_name": fiber_name,
            "access_id": access_id,
        }
        for key, val in required.items():
            if not val:
                return jsonify({"ok": False, "message": f"Parámetro {key} requerido"}), 400

        out = crear_ont_connection_intent(
            operador=operador,
            entorno_nbi=entorno_nbi or "INP",
            device_name=device_name,
            lt=lt,
            pon=pon,
            ont=ont,
            vno=vno,
            fiber_name=fiber_name,
            access_id=access_id,
            pir=ONT_CONNECTION_PIR_FIXED,
            cir=ONT_CONNECTION_CIR_FIXED,
        )
        code = 201 if out.get("ok") else 502
        return jsonify(out), code

    @app.route("/dashboard/camino-optico/consultar", methods=["POST"])
    def dash_camino_optico_consultar():
        """Dispatcher JSON para consultas del dashboard Camino Óptico."""
        data = request.get_json(silent=True) or {}
        tipo = (data.get("tipo") or "").strip().lower()
        valor = (data.get("valor") or "").strip()
        if not tipo:
            return jsonify({"error": "Parámetro tipo requerido"}), 400
        if not valor:
            return jsonify({"error": "Parámetro valor requerido"}), 400
        if tipo == "cto":
            return jsonify(dashboard_camino_optico_cto(valor))
        if tipo == "rama":
            return jsonify(dashboard_camino_optico_rama(valor))
        if tipo in ("access_id", "aid", "id"):
            return jsonify(dashboard_camino_optico_access_id(valor))
        return jsonify({"error": "tipo inválido. Use: cto, rama o access_id"}), 400
