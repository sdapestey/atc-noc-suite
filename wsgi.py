"""Entrada para Gunicorn/uWSGI: `gunicorn -w 4 -b 0.0.0.0:9002 wsgi:app`"""
from web import create_app

app = create_app()
