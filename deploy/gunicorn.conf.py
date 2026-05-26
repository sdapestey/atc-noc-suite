"""Configuración Gunicorn para ATC NOC Suite (producción, ~8 operadores)."""
import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:9000")
workers = int(os.environ.get("GUNICORN_WORKERS", max(2, min(4, multiprocessing.cpu_count()))))
threads = int(os.environ.get("GUNICORN_THREADS", "1"))
worker_class = "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "300"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "200"))
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
preload_app = os.environ.get("GUNICORN_PRELOAD", "0").lower() in ("1", "true", "yes")
