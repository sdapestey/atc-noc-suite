"""
Punto de entrada WSGI / desarrollo.

Uso: `python app.py`  |  `flask --app app run`
"""
import logging

from config import Config
from web import create_app

app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
