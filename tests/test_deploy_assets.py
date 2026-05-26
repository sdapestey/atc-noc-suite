"""Artefactos de despliegue Gunicorn + Nginx (referencia, sin levantar servicios)."""

from pathlib import Path


def test_deploy_gunicorn_and_nginx_examples_exist():
    root = Path("deploy")
    assert (root / "gunicorn.conf.py").is_file()
    assert (root / "nginx-atc-noc-suite.conf.example").is_file()
    assert (root / "atc-noc-suite.service.example").is_file()
    gunicorn = (root / "gunicorn.conf.py").read_text(encoding="utf-8")
    nginx = (root / "nginx-atc-noc-suite.conf.example").read_text(encoding="utf-8")
    assert "wsgi:app" in (root / "atc-noc-suite.service.example").read_text(encoding="utf-8")
    assert "timeout" in gunicorn
    assert "proxy_read_timeout 300s" in nginx
    assert "upstream atc_noc_suite" in nginx


def test_requirements_prod_includes_gunicorn():
    text = Path("requirements-prod.txt").read_text(encoding="utf-8")
    assert "gunicorn" in text
    assert "-r requirements.txt" in text


def test_docker_compose_files_exist():
    assert Path("Dockerfile").is_file()
    assert Path("docker-compose.yml").is_file()
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "noc-suite:" in compose
    assert "env_file:" in compose
    assert Path("deploy/nginx-docker.conf").is_file()
