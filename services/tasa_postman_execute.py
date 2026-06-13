"""Ejecuta una request del catálogo Postman TASA contra el NBI configurado."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests
from urllib.parse import urlparse

from altiplano import _extract_altiplano_error_message, obtener_token_entorno_nbi
from config import get_altiplano_nbi_target, get_altiplano_operator_credentials
from services.sn_tasa import default_tasa_serial_from_lt_pon_ont
from services.tasa_postman_catalog import (
    TASA_ONT_API_ID,
    TASA_ONT_PLUS_SERVICES_API_ID,
    TASA_SERVICES_API_ID,
    get_tasa_postman_api_by_id,
)

_API_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")
_MAX_RESPONSE_CHARS = 262_144

_FORCED_CTX_KEYS = frozenset({"protocol", "server1", "port1", "base-url1", "access-token"})


def _apply_default_serial_number(merged: dict[str, str]) -> None:
    """Si «Serial Number» viene vacío, genera ``ALCL00`` + LT + PON + ONT."""
    if str(merged.get("Serial Number") or "").strip():
        return
    sn = default_tasa_serial_from_lt_pon_ont(
        merged.get("LT"),
        merged.get("PON"),
        merged.get("ONT"),
    )
    if sn:
        merged["Serial Number"] = sn


def _substitute_postman(text: str, merged: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        return merged.get(key, m.group(0))

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", repl, text or "")


def _unresolved_placeholders(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"\{\{\s*([^}]+?)\s*\}\}", text or "")]


def _url_allowed(url: str, host: str, port: str, base: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if (p.scheme or "").lower() != "https":
        return False
    h = (p.hostname or "").strip().lower()
    if h != (host or "").strip().lower():
        return False
    uport = p.port
    if uport is None and (p.scheme or "").lower() == "https":
        uport = 443
    if str(uport or "") != str(port).strip():
        return False
    base_n = (base or "").strip().strip("/")
    path = (p.path or "").rstrip("/")
    prefix = f"/{base_n}"
    return path == prefix or path.startswith(prefix + "/")


def _content_type_from_headers(headers: dict[str, str]) -> str:
    for hk, hv in headers.items():
        if hk.lower() == "content-type":
            return hv.lower()
    return ""


def _body_request_kwargs(body_s: str, ct: str) -> dict[str, Any]:
    if not body_s.strip():
        return {}
    if "json" in ct or "yang-data+json" in ct:
        return {"json": json.loads(body_s)}
    return {"data": body_s.encode("utf-8")}


def _execute_ont_plus_services(
    variables: dict[str, str],
    *,
    collection_path: Path | None = None,
    nbi_username: str | None = None,
    nbi_password: str | None = None,
) -> dict[str, Any]:
    """POST Create ONT y luego Create Services con el mismo mapa de variables."""
    steps = (TASA_ONT_API_ID, TASA_SERVICES_API_ID)
    combined_text: list[str] = []
    last_method = "POST"
    last_url = ""
    last_status: int | None = None
    for i, sid in enumerate(steps, start=1):
        part = execute_tasa_postman_api(
            sid,
            variables,
            collection_path=collection_path,
            nbi_username=nbi_username,
            nbi_password=nbi_password,
        )
        label = "Create ONT" if sid == TASA_ONT_API_ID else "Create Services"
        block = (
            f"=== Paso {i}: {label} ({sid}) ===\n"
            f"{part.get('message') or ''}\n"
            f"HTTP {part.get('status_code')}\n"
            f"{part.get('request_method') or ''} {part.get('request_url') or ''}\n"
            f"{part.get('response_text') or ''}"
        )
        combined_text.append(block)
        last_method = str(part.get("request_method") or last_method)
        last_url = str(part.get("request_url") or last_url)
        last_status = part.get("status_code")
        if not part.get("ok"):
            joined = "\n\n".join(combined_text)
            if len(joined) > _MAX_RESPONSE_CHARS:
                joined = joined[:_MAX_RESPONSE_CHARS] + "\n…[truncado]"
            return {
                "ok": False,
                "message": f"Falló en paso {i} ({label}): {part.get('message') or 'error'}",
                "status_code": last_status,
                "response_text": joined,
                "request_method": last_method,
                "request_url": last_url,
                "failed_step": sid,
            }
    joined = "\n\n".join(combined_text)
    if len(joined) > _MAX_RESPONSE_CHARS:
        joined = joined[:_MAX_RESPONSE_CHARS] + "\n…[truncado]"
    return {
        "ok": True,
        "message": "Secuencia completada: Create ONT → Create Services",
        "status_code": last_status,
        "response_text": joined,
        "request_method": last_method,
        "request_url": last_url,
    }


def _delete_step_treat_as_success(res: requests.Response, err_msg: str) -> bool:
    """True si el borrado puede continuar (recurso ya ausente / no encontrado)."""
    if res.status_code == 404:
        return True
    low = (err_msg or "").lower()
    needles = (
        "not found",
        "does not exist",
        "doesn't exist",
        "no existe",
        "not exist",
        "unknown",
        "no intent",
    )
    return any(n in low for n in needles)


def execute_tasa_postman_api(
    api_id: str,
    variables: dict[str, str],
    *,
    collection_path: Path | None = None,
    allow_absent: bool = False,
    nbi_username: str | None = None,
    nbi_password: str | None = None,
) -> dict[str, Any]:
    """
    Autentica en NBI TASA, sustituye variables de la colección y ejecuta la request.

    ``variables`` son las del formulario (nombres con espacios, ej. «Device Name»).
    Si ``nbi_username`` / ``nbi_password`` vienen informados, autentican en lugar de ``.env``.
    """
    aid = (api_id or "").strip()
    if not aid or not _API_ID_RE.match(aid):
        return {"ok": False, "message": "api_id inválido"}

    if aid == TASA_ONT_PLUS_SERVICES_API_ID:
        return _execute_ont_plus_services(
            variables,
            collection_path=collection_path,
            nbi_username=nbi_username,
            nbi_password=nbi_password,
        )

    spec = get_tasa_postman_api_by_id(aid, collection_path)
    if not spec:
        return {"ok": False, "message": "API no encontrada en la colección TASA"}

    ui_user = (nbi_username or "").strip() if nbi_username else ""
    ui_pwd = nbi_password if isinstance(nbi_password, str) else (nbi_password or "")
    ui_pwd = ui_pwd if isinstance(ui_pwd, str) else str(ui_pwd)
    if ui_user and ui_pwd != "":
        user, pwd = ui_user, ui_pwd
    else:
        user, pwd = get_altiplano_operator_credentials("TASA")
    if not user or not pwd:
        return {"ok": False, "message": "Credenciales Altiplano TASA no configuradas (env / .env)"}

    host, port, base_url = get_altiplano_nbi_target("TASA")
    if not host or not port or not base_url:
        return {"ok": False, "message": "Destino NBI TASA no configurado"}

    token = obtener_token_entorno_nbi("TASA", user, pwd, force_refresh=bool(ui_user))
    if not token:
        return {"ok": False, "message": "No se pudo obtener token en Altiplano (TASA)"}

    merged: dict[str, str] = {}
    for k, v in (variables or {}).items():
        ks = str(k).strip()
        if ks and ks not in _FORCED_CTX_KEYS:
            merged[ks] = str(v) if v is not None else ""
    _apply_default_serial_number(merged)

    url_tmpl = str(spec.get("url_raw") or "")
    body_raw = str(spec.get("body_raw") or "")
    method = str(spec.get("method") or "GET").upper()
    raw_headers = spec.get("headers") or []

    def _run_with_token(bearer: str) -> tuple[requests.Response, str]:
        m = dict(merged)
        m["protocol"] = "https"
        m["server1"] = str(host).strip()
        m["port1"] = str(port).strip()
        m["base-url1"] = str(base_url).strip()
        m["access-token"] = str(bearer)

        url = _substitute_postman(url_tmpl, m)
        miss_url = _unresolved_placeholders(url)
        if miss_url:
            raise ValueError(f"Faltan variables en URL: {', '.join(miss_url)}")
        if not _url_allowed(url, host, port, base_url):
            raise ValueError("URL final no permitida (host/puerto/base NBI TASA)")

        body_s = _substitute_postman(body_raw, m)
        miss_body = _unresolved_placeholders(body_s)
        if miss_body:
            raise ValueError(f"Faltan variables en cuerpo: {', '.join(miss_body)}")

        headers_out: dict[str, str] = {}
        for h in raw_headers:
            if not isinstance(h, dict):
                continue
            hk = str(h.get("key") or "").strip()
            if not hk or hk.lower() == "authorization":
                continue
            hv = _substitute_postman(str(h.get("value") or ""), m)
            miss_h = _unresolved_placeholders(hv)
            if miss_h:
                raise ValueError(f"Faltan variables en cabecera «{hk}»: {', '.join(miss_h)}")
            headers_out[hk] = hv

        headers_out["Authorization"] = f"Bearer {bearer}"
        ct = _content_type_from_headers(headers_out)
        try:
            body_kw = _body_request_kwargs(body_s, ct)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON de cuerpo inválido tras sustituir variables: {exc}") from exc

        res = requests.request(
            method,
            url,
            headers=headers_out,
            verify=False,
            timeout=120,
            **body_kw,
        )
        return res, url

    try:
        res, final_url = _run_with_token(token)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    except requests.RequestException as exc:
        return {"ok": False, "message": f"Error de red: {exc}"}

    if res.status_code == 401:
        new_tok = obtener_token_entorno_nbi("TASA", user, pwd, force_refresh=True)
        if not new_tok:
            text_out = (res.text or "")[:_MAX_RESPONSE_CHARS]
            return {
                "ok": False,
                "message": "401 No autorizado y no se pudo renovar el token",
                "status_code": 401,
                "response_text": text_out,
                "request_method": method,
                "request_url": final_url,
            }
        try:
            res, final_url = _run_with_token(new_tok)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        except requests.RequestException as exc:
            return {"ok": False, "message": f"Error de red (reintento): {exc}"}

    text_out = res.text or ""
    if len(text_out) > _MAX_RESPONSE_CHARS:
        text_out = text_out[:_MAX_RESPONSE_CHARS] + "\n…[truncado]"

    ok_http = 200 <= res.status_code < 300
    out: dict[str, Any] = {
        "ok": ok_http,
        "status_code": res.status_code,
        "response_text": text_out,
        "request_method": method,
        "request_url": final_url,
    }
    if ok_http:
        out["message"] = f"HTTP {res.status_code}"
        return out

    msg = _extract_altiplano_error_message(res)
    if allow_absent and _delete_step_treat_as_success(res, msg):
        out["ok"] = True
        out["skipped"] = True
        out["message"] = f"HTTP {res.status_code} (ausente, se continúa): {msg}"
        return out

    out["message"] = f"HTTP {res.status_code}: {msg}"
    return out
