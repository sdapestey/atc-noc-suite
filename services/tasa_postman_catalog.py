"""Catálogo de requests TASA desde colección Postman v2.1 (Orquestador VNO)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from config import get_altiplano_nbi_target

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_COLLECTION = _REPO_ROOT / "data" / "postman" / "tasa_prod_altiplano.postman_collection.json"

_SKIP_NAMES = frozenset(
    {
        "getaccesstoken",
        "logout",
    }
)

_POSTMAN_VAR_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")

# Variables de entorno Postman que el servidor resuelve (no se muestran en el formulario).
_TASA_HIDDEN_POSTMAN_KEYS = frozenset(
    {
        "protocol",
        "server1",
        "port1",
        "base-url1",
        "access-token",
        "refresh-token",
        "username",
        "password",
    }
)

# APIs de la colección Postman (slugs) usadas en el flujo compuesto del wizard.
TASA_ONT_API_ID = "configure-create-ont"
TASA_SERVICES_API_ID = "configure-create-services"
TASA_ONT_PLUS_SERVICES_API_ID = "configure-create-ont-plus-services"
TASA_DELETE_SERVICES_API_ID = "unconfigure-delete-services"
TASA_DELETE_ONT_API_ID = "unconfigure-delete-ont"
TASA_MODIFY_PROFILES_API_ID = "modify-modify-profiles"
_TASA_ONT_SERVICES_REPLACE_IDS = frozenset({TASA_ONT_API_ID, TASA_SERVICES_API_ID})


def build_tasa_ont_plus_services_composite(apis: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Una sola opción de menú que une «Create ONT» y «Create Services» (mismas variables combinadas).
    """
    by_id = {str(a.get("id") or ""): a for a in apis if a.get("id")}
    ont = by_id.get(TASA_ONT_API_ID)
    svc = by_id.get(TASA_SERVICES_API_ID)
    if not isinstance(ont, dict) or not isinstance(svc, dict):
        return None
    seen: set[str] = set()
    form_vars: list[str] = []
    for k in list(ont.get("form_variables") or []):
        if k not in seen:
            seen.add(k)
            form_vars.append(k)
    for k in list(svc.get("form_variables") or []):
        if k not in seen:
            seen.add(k)
            form_vars.append(k)
    var_keys = ordered_postman_var_keys(
        str(ont.get("url_raw") or ""),
        str(ont.get("body_raw") or ""),
        *[h.get("value", "") for h in (ont.get("headers") or []) if isinstance(h, dict)],
        str(svc.get("url_raw") or ""),
        str(svc.get("body_raw") or ""),
        *[h.get("value", "") for h in (svc.get("headers") or []) if isinstance(h, dict)],
    )
    return {
        "id": TASA_ONT_PLUS_SERVICES_API_ID,
        "label": "Configure / Create ONT + Services",
        "folder": "Configure",
        "request_name": "Create ONT + Services",
        "method": "POST",
        "url_raw": "",
        "body_raw": "",
        "headers": [],
        "variables": var_keys,
        "form_variables": form_vars,
    }


def apply_tasa_wizard_api_list_overrides(apis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sustituye Create ONT + Create Services por una sola entrada compuesta en el asistente."""
    composite = build_tasa_ont_plus_services_composite(apis)
    if not composite:
        return apis
    rest = [a for a in apis if a.get("id") not in _TASA_ONT_SERVICES_REPLACE_IDS]
    return [composite] + rest


def default_tasa_postman_collection_path() -> Path:
    raw = (os.environ.get("TASA_POSTMAN_COLLECTION_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_COLLECTION


def _url_raw_from_request(request: dict[str, Any]) -> str:
    u = request.get("url")
    if isinstance(u, str):
        return u
    if isinstance(u, dict):
        return str(u.get("raw") or "")
    return ""


def _body_raw_from_request(request: dict[str, Any]) -> str:
    body = request.get("body")
    if isinstance(body, dict) and body.get("mode") == "raw":
        return str(body.get("raw") or "")
    return ""


def _headers_from_request(request: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for h in request.get("header") or []:
        if not isinstance(h, dict):
            continue
        if h.get("disabled") is True:
            continue
        key = str(h.get("key") or "").strip()
        if not key:
            continue
        rows.append({"key": key, "value": str(h.get("value") or "")})
    return rows


def ordered_postman_var_keys(*chunks: str) -> list[str]:
    """Orden de aparición en plantillas Postman (``{{var}}``), sin duplicados."""
    seen: set[str] = set()
    out: list[str] = []
    for ch in chunks:
        if not ch:
            continue
        for m in _POSTMAN_VAR_RE.finditer(ch):
            key = m.group(1).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def _walk_items(
    items: list[Any],
    folder_stack: list[str],
    out: list[dict[str, Any]],
) -> None:
    for it in items or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        sub = it.get("item")
        if isinstance(sub, list) and sub:
            _walk_items(sub, folder_stack + ([name] if name else []), out)
            continue
        req = it.get("request")
        if not isinstance(req, dict):
            continue
        if not name or name.lower() in _SKIP_NAMES:
            continue
        folder = folder_stack[0] if folder_stack else ""
        label = f"{folder} / {name}" if folder else name
        slug = re.sub(r"[^a-z0-9]+", "-", f"{folder}-{name}".lower()).strip("-")
        method = str(req.get("method") or "GET").strip().upper() or "GET"
        url_raw = _url_raw_from_request(req)
        body_raw = _body_raw_from_request(req)
        headers = _headers_from_request(req)
        hvals = [h["value"] for h in headers]
        var_keys = ordered_postman_var_keys(url_raw, body_raw, *hvals)
        out.append(
            {
                "id": slug or name.lower().replace(" ", "-"),
                "label": label,
                "folder": folder,
                "request_name": name,
                "method": method,
                "url_raw": url_raw,
                "body_raw": body_raw,
                "headers": headers,
                "variables": var_keys,
                "form_variables": [k for k in var_keys if k not in _TASA_HIDDEN_POSTMAN_KEYS],
            }
        )


def load_tasa_postman_api_list(path: Path | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """Devuelve ``(apis, error)`` donde ``error`` es mensaje si falla lectura/parseo."""
    p = path or default_tasa_postman_collection_path()
    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
    except OSError as exc:
        return [], f"No se pudo leer la colección Postman ({p}): {exc}"
    except json.JSONDecodeError as exc:
        return [], f"JSON inválido en {p}: {exc}"
    if not isinstance(data, dict):
        return [], "La colección Postman no es un objeto JSON."
    items = data.get("item")
    if not isinstance(items, list):
        return [], "La colección no tiene clave «item»."
    out: list[dict[str, Any]] = []
    _walk_items(items, [], out)
    return out, None


def get_tasa_postman_api_by_id(api_id: str, path: Path | None = None) -> dict[str, Any] | None:
    """Devuelve la entrada del catálogo para ``api_id`` o ``None``."""
    aid = (api_id or "").strip()
    if not aid:
        return None
    apis, err = load_tasa_postman_api_list(path)
    if err:
        return None
    for a in apis:
        if a.get("id") == aid:
            return a
    return None


def tasa_entorno_display_label() -> str:
    """Texto para el paso «entorno» (NBI TASA según config / env)."""
    custom = (os.environ.get("ALTIPLANO_TASA_ENV_LABEL") or "").strip()
    if custom:
        return custom
    host, _port, base = get_altiplano_nbi_target("TASA")
    host = host or "—"
    base = base or "—"
    return f"Producción · {base} ({host})"


def build_tasa_vno_wizard_context() -> dict[str, Any]:
    apis, err = load_tasa_postman_api_list()
    collection_name = "TASA - PROD ALTIPLANO"
    p = default_tasa_postman_collection_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        info = data.get("info") if isinstance(data, dict) else None
        if isinstance(info, dict) and info.get("name"):
            collection_name = str(info["name"]).strip() or collection_name
    except (OSError, json.JSONDecodeError):
        pass
    host, port, base = get_altiplano_nbi_target("TASA")
    if not err:
        apis = apply_tasa_wizard_api_list_overrides(apis)
    return {
        "tasa_postman_collection_name": collection_name,
        "tasa_postman_apis": apis,
        "tasa_postman_catalog_error": err,
        "tasa_nbi_entorno_label": tasa_entorno_display_label(),
        "tasa_nbi_host": host,
        "tasa_nbi_port": port,
        "tasa_nbi_base": base,
    }
