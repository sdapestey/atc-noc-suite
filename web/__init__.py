"""Aplicación Flask (factory)."""
import atexit
import logging
import os
from flask import Flask, request

from config import Config, get_noc_wiki_url
from db import close_pool

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def create_app() -> Flask:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = Flask(
        __name__,
        template_folder=os.path.join(_ROOT, "templates"),
        static_folder=os.path.join(_ROOT, "static"),
    )
    app.config.from_object(Config)

    if not Config.DEBUG and Config.SECRET_KEY == "dev-only-change-in-production":
        app.logger.warning(
            "SECRET_KEY sigue siendo el valor por defecto; definí SECRET_KEY en el entorno en producción."
        )

    @app.after_request
    def add_security_headers(resp):
        """Cabeceras defensivas base para reducir superficie de ataque en navegador."""
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault(
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), microphone=(), payment=(), usb=()",
        )
        max_age = int(getattr(Config, "STATIC_CACHE_MAX_AGE", 0) or 0)
        if max_age > 0 and request.path.startswith("/static/"):
            resp.headers.setdefault("Cache-Control", f"public, max-age={max_age}")
        return resp

    @app.context_processor
    def inject_nav_tab():
        p = request.path or ""
        if p.startswith("/dashboard/rama"):
            tab = "rama"
        elif p.startswith("/dashboard/olt"):
            tab = "olt"
        elif p.startswith("/dashboard/camino-optico"):
            tab = "camino"
        elif p.startswith("/dashboard/altiplano"):
            tab = "altiplano"
        elif p.startswith("/dashboard/potencias-historico"):
            tab = "historico"
        elif p.startswith("/dashboard/calidad-inventario"):
            tab = "calidad"
        else:
            tab = "index"
        labels = {
            "index": "Consulta",
            "rama": "RAMA / CTO",
            "olt": "OLT / LT",
            "camino": "Camino Optico",
            "historico": "Historico Potencias",
            "calidad": "Calidad Inventario",
            "altiplano": "Orquestador",
        }
        return {
            "nav_tab": tab,
            "nav_tab_label": labels.get(tab, "Consulta"),
            "noc_wiki_url": get_noc_wiki_url(),
        }

    from . import routes

    routes.register(app)

    atexit.register(close_pool)
    return app
