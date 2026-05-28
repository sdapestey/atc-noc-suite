"""Cliente Web ToolBox FTTH Norte — envío de CTO (SendFTTH)."""
from __future__ import annotations

import json
from typing import Any

import requests

from config import get_ftth_toolbox_config

_DEFAULT_TIMEOUT_S = 90
_USER_AGENT = (
    "Mozilla/5.0 (compatible; atc-noc-suite/1.0; +https://github.com/atc-noc-suite)"
)


def _parse_send_ftth_response(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {
            "code": None,
            "description": "Respuesta vacía del ToolBox",
            "raw_response": None,
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "code": None,
            "description": raw[:500],
            "raw_response": raw[:2000],
        }
    if not isinstance(data, dict):
        return {
            "code": None,
            "description": "Formato de respuesta inesperado",
            "raw_response": data,
        }
    return {
        "code": data.get("Code"),
        "description": data.get("Description") or data.get("description") or "",
        "raw_response": data.get("RawResponse"),
        "payload": data,
    }


def _toolbox_session(base_url: str) -> requests.Session:
    sess = requests.Session()
    sess.headers.update(
        {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.5",
        }
    )
    sess.verify = True
    return sess


def _login_toolbox(sess: requests.Session, base_url: str, user: str, password: str) -> str | None:
    login_url = f"{base_url}/login/login_ingreso"
    try:
        res = sess.post(
            login_url,
            data={"login": user, "password": password},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
                "Referer": f"{base_url}/",
            },
            timeout=30,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        return f"No se pudo autenticar en ToolBox: {exc}"
    if res.status_code not in (200, 302, 303):
        return f"Login ToolBox falló (HTTP {res.status_code})"
    if not sess.cookies:
        return "Login ToolBox sin cookie de sesión"
    return None


def enviar_cto_ftth_toolbox(
    *,
    cto_id: str,
    access_id: str,
    ally_id: str | None = None,
    drop_id: str = "",
    num_serie: str = "",
    activity_id: str = "",
) -> dict[str, Any]:
    """
    Replica ``POST /index.php/Ftthnorte/SendFTTH`` (proceso «Enviar CTO», tipo ``cto``).

    Parámetros alineados con el mantenedor FTTH Norte de ar-toolbox.simpledatacorp.com.
    """
    cto_id = (cto_id or "").strip()
    access_id = (access_id or "").strip()
    if not cto_id:
        return {"ok": False, "message": "CTO ID en NFC requerido"}
    if not access_id:
        return {"ok": False, "message": "Access ID requerido"}

    cfg = get_ftth_toolbox_config()
    base_url = cfg.get("base_url") or ""
    user = cfg.get("user") or ""
    password = cfg.get("password") or ""
    ally = (ally_id or cfg.get("ally_atc_id") or "8").strip()

    if not base_url:
        return {"ok": False, "message": "FTTH_TOOLBOX_BASE_URL no configurado"}
    if not user or not password:
        return {
            "ok": False,
            "message": (
                "Credenciales ToolBox no configuradas "
                "(FTTH_TOOLBOX_USER / FTTH_TOOLBOX_PASSWORD en .env)"
            ),
        }

    sess = _toolbox_session(base_url)
    login_err = _login_toolbox(sess, base_url, user, password)
    if login_err:
        return {"ok": False, "message": login_err}

    index_url = f"{base_url}/Ftthnorte/index"
    try:
        sess.get(index_url, timeout=30)
    except requests.RequestException:
        pass

    send_url = f"{base_url}/index.php/Ftthnorte/SendFTTH"
    form = {
        "ctoid": cto_id,
        "dropid": (drop_id or "").strip(),
        "accessid": access_id,
        "numserie": (num_serie or "").strip(),
        "tipo": "cto",
        "idactivity": (activity_id or "").strip(),
        "allyid": ally,
    }
    try:
        res = sess.post(
            send_url,
            data=form,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": base_url,
                "Referer": index_url,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/plain, */*; q=0.01",
            },
            timeout=_DEFAULT_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        return {
            "ok": False,
            "message": f"Error al llamar SendFTTH: {exc}",
            "request": form,
        }

    parsed = _parse_send_ftth_response(res.text)
    code = parsed.get("code")
    description = str(parsed.get("description") or "").strip()
    ok = res.status_code == 200 and str(code) == "0"
    msg = description or (
        "CTO enviado correctamente" if ok else f"ToolBox respondió código {code!r}"
    )
    out: dict[str, Any] = {
        "ok": ok,
        "message": msg,
        "http_status": res.status_code,
        "toolbox_code": code,
        "toolbox_description": description,
        "toolbox_raw_response": parsed.get("raw_response"),
        "request": form,
    }
    if parsed.get("payload") is not None:
        out["toolbox_payload"] = parsed["payload"]
    if not ok and res.status_code >= 500:
        out["message"] = description or f"Error HTTP {res.status_code} en ToolBox"
    return out
