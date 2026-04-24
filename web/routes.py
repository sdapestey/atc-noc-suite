"""Registro de rutas HTTP de la aplicación Flask.

Este módulo concentra la capa web: parsea requests, valida entradas,
invoca servicios y devuelve templates o JSON según corresponda.
"""
from datetime import datetime, timezone

from flask import Response, jsonify, redirect, render_template, request, url_for
from urllib.parse import quote_plus

from db import healthcheck_db
from services import (
    cambiar_sn_ont,
    consultar_access_id_desde_alias,
    consultar_access_id_baja_o_ausente,
    consultar_access_id_detalle_desde_bajada_inventario,
    consultar_access_id_estructura,
    consultar_access_id_potencias,
    consultar_cto_coordenadas,
    consultar_cto_estructura,
    consultar_cto_potencias,
    consultar_dashboard_rama,
    consultar_rama_estructura,
    consultar_rama_potencias,
    dashboard_camino_optico_access_id,
    dashboard_camino_optico_cto,
    dashboard_camino_optico_rama,
    dashboard_olts,
    dashboard_ramas,
    crear_ont_connection_intent,
    estructura_dashboard_lt,
    export_dashboard_olts_csv,
    export_dashboard_ramas_csv,
    export_index_query_csv,
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


def register(app):
    """Registra todas las rutas HTTP en la app Flask.

    Además define constantes de negocio acotadas al contexto web
    (por ejemplo, valores fijos para intents de Altiplano).
    """
    ONT_CONNECTION_PIR_FIXED = 1000
    ONT_CONNECTION_CIR_FIXED = 35

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
        return redirect(url_for("index"))

    @app.route("/", methods=["GET", "POST"])
    def index():
        value = ""
        resultado = None
        tabla_cto = None
        es_rama = False
        ruta = {"aid": None, "cto": None, "rama": None}
        cto_maps_url = None
        busqueda_aid = None

        if request.method == "POST":
            value = request.form.get("value", "").strip()

            value_upper = value.upper()

            if value.isdigit():
                # Solo dígitos: aux.bajada_inventario → detalle; si no, aux.bajas_de_inventario y
                # aux.bajas_inventario → banner de baja; si no, no existe en ATC.
                resultado = consultar_access_id_detalle_desde_bajada_inventario(value)
                busqueda_aid = None
                if resultado:
                    cto_maps_url = _update_route_and_maps_from_result(resultado, ruta)
                else:
                    busqueda_aid = consultar_access_id_baja_o_ausente(value)

            elif "FATC" in value_upper:
                tabla_cto = consultar_cto_estructura(value)
                ruta["cto"] = value
                coords = consultar_cto_coordenadas(value)
                if coords:
                    lat_lon = f"{coords['lat']},{coords['lon']}"
                    cto_maps_url = (
                        "https://www.google.com/maps/search/?api=1&query="
                        f"{quote_plus(lat_lon)}"
                    )

            elif "RATC" in value_upper:
                tabla_cto = consultar_rama_estructura(value)
                es_rama = True
                ruta["rama"] = value

            elif (
                value_upper.startswith("SRVC_LOC_")
                or value_upper.startswith("RES_MT_")
                or value_upper.startswith("RES_IP_")
            ):
                resultado = consultar_access_id_desde_alias(value)
                busqueda_aid = None
                if resultado:
                    cto_maps_url = _update_route_and_maps_from_result(resultado, ruta)
                else:
                    busqueda_aid = {"tipo": "no_existe", "AID": value}

        return render_template(
            "index.html",
            resultado=resultado,
            tabla_cto=tabla_cto,
            es_rama=es_rama,
            value=value,
            ruta=ruta,
            cto_maps_url=cto_maps_url,
            busqueda_aid=busqueda_aid,
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
        return Response(
            "\ufeff" + data,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=consulta.csv"},
        )

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

    @app.route("/dashboard/rama/export.csv")
    def export_rama_csv():
        data = export_dashboard_ramas_csv()
        return Response(
            "\ufeff" + data,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=dashboard_ramas.csv"},
        )

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
        return Response(
            "\ufeff" + data,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=dashboard_olts.csv"},
        )

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
