"""Registro de rutas HTTP."""
from datetime import datetime, timezone

from flask import Response, jsonify, redirect, render_template, request, url_for
from urllib.parse import quote_plus

from db import healthcheck_db
from services import (
    cambiar_sn_ont,
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
    estructura_dashboard_lt,
    export_dashboard_olts_csv,
    export_dashboard_ramas_csv,
    export_index_query_csv,
)


def register(app):
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

            if value.isdigit():
                # Solo dígitos: aux.bajada_inventario → detalle; si no, aux.bajas_de_inventario y
                # aux.bajas_inventario → banner de baja; si no, no existe en ATC.
                resultado = consultar_access_id_detalle_desde_bajada_inventario(value)
                busqueda_aid = None
                if resultado:
                    ruta["aid"] = resultado["AID"]
                    ruta["cto"] = resultado["CTO"]
                    ruta["rama"] = resultado.get("RAMA")
                    if resultado.get("CTO") and resultado["CTO"] != "—":
                        coords = consultar_cto_coordenadas(resultado["CTO"])
                        if coords:
                            lat_lon = f"{coords['lat']},{coords['lon']}"
                            cto_maps_url = (
                                "https://www.google.com/maps/search/?api=1&query="
                                f"{quote_plus(lat_lon)}"
                            )
                else:
                    busqueda_aid = consultar_access_id_baja_o_ausente(value)

            elif "FATC" in value:
                tabla_cto = consultar_cto_estructura(value)
                ruta["cto"] = value
                coords = consultar_cto_coordenadas(value)
                if coords:
                    lat_lon = f"{coords['lat']},{coords['lon']}"
                    cto_maps_url = (
                        "https://www.google.com/maps/search/?api=1&query="
                        f"{quote_plus(lat_lon)}"
                    )

            elif "RATC" in value:
                tabla_cto = consultar_rama_estructura(value)
                es_rama = True
                ruta["rama"] = value

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
        valor = (request.form.get("value") or "").strip()
        if not valor:
            return jsonify({"error": "Parámetro value requerido"}), 400

        if valor.isdigit():
            return jsonify(consultar_access_id_potencias(valor))

        if "FATC" in valor:
            return jsonify(consultar_cto_potencias(valor))

        if "RATC" in valor:
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

    @app.route("/dashboard/camino-optico/consultar", methods=["POST"])
    def dash_camino_optico_consultar():
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
