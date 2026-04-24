"""Aplicación Flask (factory)."""
import atexit
import logging
import os
from datetime import datetime

from flask import Flask, request

from config import Config
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

    @app.context_processor
    def noc_page_time():
        return {"page_generated_at": datetime.now().strftime("%d/%m/%Y %H:%M")}

    @app.context_processor
    def inject_nav_tab():
        p = request.path or ""
        if p.startswith("/dashboard/rama"):
            tab = "rama"
        elif p.startswith("/dashboard/olt"):
            tab = "olt"
        elif p.startswith("/dashboard/camino-optico"):
            tab = "camino"
        else:
            tab = "index"
        return {"nav_tab": tab}

    from . import routes

    routes.register(app)

    atexit.register(close_pool)
    return app
