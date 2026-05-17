"""Borrado INP ont-connection precedido de unconfigure TASA en NBI (services → ONT)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from altiplano import (
    _extract_intent_list_from_search_intents_response,
    _json_loads_altiplano_http_response,
    _unwrap_restconf_data_layer,
    borrar_intent_ont_connection_inp,
    buscar_intents_ont_connection_inp,
    obtener_token_entorno_nbi,
)
from config import (
    get_altiplano_nbi_target,
    get_altiplano_operator_credentials,
    get_altiplano_tasa_discovery_search_timeout_s,
    get_altiplano_tasa_discovery_wide_list_enabled,
    get_altiplano_tasa_discovery_wide_list_timeout_s,
    get_altiplano_tasa_intent_restconf_paths,
)
from services.domain import OPERADORES
from services.inventory import resolver_target_ont_connection_por_access_id
from services.tasa_postman_catalog import TASA_DELETE_ONT_API_ID, TASA_DELETE_SERVICES_API_ID
from services.tasa_postman_execute import execute_tasa_postman_api

logger = logging.getLogger(__name__)

# ``BA_OLTA_ES01_01-1-1-99`` o ``…-1-1-99#1001#gpon``
_LOCATION_TARGET_RE = re.compile(
    r"^(?P<device>BA_OLTA_.+)-(?P<lt>\d+)-(?P<pon>\d+)-(?P<ont>\d+)"
    r"(?:#(?P<vno>\d+)#gpon)?$",
    re.IGNORECASE,
)
_ONT_CONNECTION_VNO_SUFFIX_RE = re.compile(r"#(\d+)#gpon\s*$", re.IGNORECASE)
_RESTCONF_INTENT_KEY_RE = re.compile(
    r"^(?P<target>.+#HSI-[^#,]+),(?P<intent_type>tasa-composite)$",
    re.IGNORECASE,
)
_TASA_WIDE_LIST_PARAMS: tuple[dict[str, str], ...] = (
    {"depth": "1"},
    {},
)


def parse_olt_location_target(raw: str) -> dict[str, Any] | None:
    """Extrae device, LT, PON, ONT y VNO opcional desde prefijo o target ont-connection."""
    s = (raw or "").strip()
    if not s:
        return None
    m = _LOCATION_TARGET_RE.match(s)
    if not m and "#" in s:
        m = _LOCATION_TARGET_RE.match(s.split("#", 1)[0])
    if not m:
        return None
    vno_s = m.group("vno")
    vno = int(vno_s) if vno_s else None
    if vno is None and "#" in s:
        parts = s.split("#")
        if len(parts) >= 2 and parts[1].isdigit():
            vno = int(parts[1])
    return {
        "device_name": m.group("device"),
        "lt": m.group("lt"),
        "pon": m.group("pon"),
        "ont": m.group("ont"),
        "vno": vno,
        "location_prefix": f"{m.group('device')}-{m.group('lt')}-{m.group('pon')}-{m.group('ont')}",
    }


def _vno_operator(vno: int | None) -> str | None:
    if vno is None:
        return None
    return OPERADORES.get(vno)


def _vno_id_from_ont_connection_target(target: str) -> int | None:
    m = _ONT_CONNECTION_VNO_SUFFIX_RE.search((target or "").strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _resolve_vno_via_inp_search(
    sess_token: str,
    *,
    device_prefix: str | None,
    access_id: str | None,
) -> dict[str, Any]:
    """Consulta INP para derivar VNO desde el target ``…#{VNO}#gpon`` del intent."""
    search = buscar_intents_ont_connection_inp(
        sess_token,
        device_prefix=(device_prefix or "").strip() or None,
        access_id=(access_id or "").strip() or None,
    )
    if not search.get("ok"):
        return {
            "ok": False,
            "message": search.get("message") or "No se pudo consultar INP para detectar VNO.",
        }
    matches = search.get("matches") or []
    if not matches:
        return {
            "ok": False,
            "message": (
                "No se encontró ont-connection en INP. Verificá device name / Access ID "
                "o usá el target completo tipo …#1001#gpon."
            ),
        }
    if len(matches) > 1:
        return {
            "ok": False,
            "message": (
                "Varios intents ont-connection coinciden; acotá con Access ID "
                "o target completo …#VNO#gpon."
            ),
            "matches": matches,
        }
    target = str(matches[0].get("target") or "").strip()
    vno = _vno_id_from_ont_connection_target(target)
    if vno is None:
        return {
            "ok": False,
            "message": f"Target INP sin VNO reconocible: {target or '—'}",
        }
    return {"ok": True, "vno": vno, "inp_target": target}


def resolve_borrado_cascade_context(
    device_name: str,
    by_id: str,
    *,
    sess_token: str | None = None,
) -> dict[str, Any]:
    """
    Arma criterio INP y variables VNO a partir de device/target o Access ID (inventario).
    """
    dn = (device_name or "").strip()
    aid = (by_id or "").strip()
    inventory_resolution = None

    parsed = parse_olt_location_target(dn) if dn else None
    if not parsed and dn and "#" in dn:
        parsed = parse_olt_location_target(dn)

    inp_device = dn
    if aid and not parsed:
        inv = resolver_target_ont_connection_por_access_id(aid)
        if not inv.get("ok"):
            return {
                "ok": False,
                "message": inv.get("message") or "No se pudo resolver Access ID en inventario.",
            }
        inventory_resolution = {k: v for k, v in inv.items() if k != "ok"}
        loc = str(inv.get("device_location_prefix") or "").strip()
        parsed = parse_olt_location_target(loc) if loc else None
        try:
            vno_from_inv = int(inv["invocator_system"]) if inv.get("invocator_system") is not None else None
        except (TypeError, ValueError):
            vno_from_inv = None
        if parsed and vno_from_inv is not None:
            parsed["vno"] = vno_from_inv
        inp_device = str(inv.get("device_name_for_query") or loc or dn).strip()
        if not dn:
            dn = inp_device

    if not parsed:
        return {
            "ok": False,
            "message": (
                "No se pudo derivar Device Name / LT / PON / ONT. "
                "Usá un prefijo tipo BA_OLTA_ES01_01-1-1-99 o un Access ID con inventario."
            ),
        }

    if not inp_device:
        vno = parsed.get("vno")
        suffix = f"#{vno}#gpon" if vno is not None else ""
        inp_device = f"{parsed['location_prefix']}{suffix}"

    inp_vno_resolution = None
    if parsed.get("vno") is None and (sess_token or "").strip():
        vno_hit = _resolve_vno_via_inp_search(
            sess_token,
            device_prefix=parsed.get("location_prefix"),
            access_id=aid or None,
        )
        if not vno_hit.get("ok"):
            out_err: dict[str, Any] = {
                "ok": False,
                "message": vno_hit.get("message") or "No se pudo detectar VNO.",
            }
            if vno_hit.get("matches"):
                out_err["matches"] = vno_hit["matches"]
            return out_err
        parsed["vno"] = vno_hit["vno"]
        inp_vno_resolution = {
            "vno": vno_hit["vno"],
            "inp_target": vno_hit.get("inp_target"),
        }
        if "#" not in inp_device or inp_device.count("#") < 2:
            inp_device = str(vno_hit.get("inp_target") or inp_device).strip()

    operator = _vno_operator(parsed.get("vno"))
    if operator is None:
        vno_code = parsed.get("vno")
        return {
            "ok": False,
            "message": (
                f"VNO {vno_code} no tiene cascada de borrado automática en este orquestador. "
                "Indicá target …#VNO#gpon conocido o contactá soporte."
            ),
        }
    return {
        "ok": True,
        "inp_device_prefix": inp_device,
        "access_id": aid or None,
        "vno_variables": {
            "Device Name": parsed["device_name"],
            "LT": parsed["lt"],
            "PON": parsed["pon"],
            "ONT": parsed["ont"],
        },
        "vno_code": parsed.get("vno"),
        "operator": operator,
        "inventory_resolution": inventory_resolution,
        "inp_vno_resolution": inp_vno_resolution,
    }


def _intent_from_restconf_map_key(key: str) -> dict[str, str] | None:
    """Clave RESTCONF típica: ``BA_OLTA_…-1-1-2#HSI-100,tasa-composite``."""
    s = (key or "").strip()
    if not s:
        return None
    m = _RESTCONF_INTENT_KEY_RE.match(s)
    if not m:
        if "," not in s or "#hsi-" not in s.lower():
            return None
        target, intent_type = s.split(",", 1)
        target, intent_type = target.strip(), intent_type.strip()
        if not target or intent_type.lower() != "tasa-composite":
            return None
        return {"target": target, "intent-type": intent_type}
    return {
        "target": m.group("target").strip(),
        "intent-type": m.group("intent_type").strip(),
    }


def extract_hsi_svlans_deep(payload: object, location_prefix: str) -> list[str]:
    """
    Recorre JSON RESTCONF/search y extrae SVLAN de ``{prefix}#HSI-{svlan}``
    (campos, claves de mapa y strings embebidos).
    """
    prefix = (location_prefix or "").strip()
    if not prefix:
        return []
    esc = re.escape(prefix)
    pat_any = re.compile(rf"{esc}#HSI-(?P<svlan>[^#,\s\"]+)", re.IGNORECASE)
    found: set[str] = set()

    def walk(o: object) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str):
                    parsed = _intent_from_restconf_map_key(k)
                    if parsed and parsed["target"].lower().startswith(f"{prefix.lower()}#hsi-"):
                        for m in pat_any.finditer(parsed["target"]):
                            found.add(m.group("svlan").strip())
                    for m in pat_any.finditer(k):
                        found.add(m.group("svlan").strip())
                walk(v)
        elif isinstance(o, list):
            for item in o:
                walk(item)
        elif isinstance(o, str) and prefix.lower() in o.lower():
            for m in pat_any.finditer(o):
                found.add(m.group("svlan").strip())

    walk(payload)
    return sorted(found, key=lambda s: (len(s), s))


def _collect_tasa_composite_intents(obj: object, out: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                parsed_key = _intent_from_restconf_map_key(k)
                if parsed_key and parsed_key.get("intent-type", "").lower() == "tasa-composite":
                    entry = dict(parsed_key)
                    if isinstance(v, dict):
                        entry.update(v)
                    out.append(entry)
        it = str(obj.get("intent-type") or "").strip().lower()
        if it in ("tasa-composite",) and obj.get("target"):
            out.append(obj)
        for val in obj.values():
            _collect_tasa_composite_intents(val, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_tasa_composite_intents(item, out)


def _svlans_from_tasa_composite_intents(
    intents: list[dict[str, Any]],
    location_prefix: str,
) -> list[str]:
    """Extrae SVLAN de targets ``{prefix}#HSI-{svlan}``."""
    prefix = (location_prefix or "").strip()
    if not prefix:
        return []
    needle = f"{prefix}#HSI-"
    seen: set[str] = set()
    out: list[str] = []
    for it in intents:
        t = str(it.get("target") or "").strip()
        if not t.upper().startswith(needle.upper()):
            continue
        rest = t[len(prefix) :]
        if not rest.upper().startswith("#HSI-"):
            continue
        svlan = rest[5:].split("#", 1)[0].strip()
        if svlan and svlan not in seen:
            seen.add(svlan)
            out.append(svlan)
    return out


def _merge_unique_svlans(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for sv in group:
            s = (sv or "").strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


def _tasa_rest_bases() -> tuple[str, str] | None:
    host, port, base_url = get_altiplano_nbi_target("TASA")
    if not host or not port or not base_url:
        return None
    data = f"https://{host}:{port}/{base_url}/rest/restconf/data"
    ops = data.replace("/rest/restconf/data", "/rest/restconf/operations")
    return data, ops


def _tasa_auth_headers() -> tuple[dict[str, str], str] | None:
    user, pwd = get_altiplano_operator_credentials("TASA")
    if not user or not pwd:
        return None
    token = obtener_token_entorno_nbi("TASA", user, pwd)
    if not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/yang-data+json, application/json;q=0.9, */*;q=0.5",
        "Content-Type": "application/yang-data+json",
    }
    return headers, token


def _tasa_gui_search_intents_body(
    location_prefix: str,
    *,
    intent_type: str = "tasa-composite",
    intent_type_version: str = "3",
    page_size: int = 50,
) -> dict[str, Any]:
    """
    Mismo cuerpo que la GUI TASA (HAR ``search-intents``): filtro ES + target CONTAINS.

    Ejemplo de respuesta: ``target``: ``BA_OLTA_ES01_01-1-1-2#HSI-1501`` → SVLAN ``1501``.
    """
    return {
        "ibn:search-intents": {
            "search-from": "ES",
            "page-number": 0,
            "page-size": page_size,
            "filter": {
                "device-name": [],
                "target": location_prefix,
                "label": [],
                "config-required": True,
                "state-required": False,
                "predicate": "CONTAINS",
                "relative-object-id": [],
                "intent-type-list": [
                    {
                        "intent-type": intent_type,
                        "intent-type-version": intent_type_version,
                    }
                ],
                "required-network-state": [],
                "health": [],
                "order-by-input": {"direction": "asc", "argument": "target"},
            },
        }
    }


def _tasa_search_intents_bodies(prefix: str, access_id: str | None) -> list[dict[str, Any]]:
    bodies: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(body: dict[str, Any]) -> None:
        key = json.dumps(body, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            bodies.append(body)

    # Formato GUI (Altiplano TASA prod) — prioridad máxima.
    add(_tasa_gui_search_intents_body(prefix))

    aid = (access_id or "").strip()
    if aid:
        add({"ibn:input": {"intent-type": "tasa-composite", "access-id": aid}})
        add({"ibn:input": {"access-id": aid, "intent-type": "tasa-composite"}})
    # Fallback legacy RESTCONF (otros releases / INP-style).
    add({"ibn:input": {"intent-type": "tasa-composite", "target": prefix}})
    add({"ibn:input": {"intent-type": "tasa-composite", "intent-target": prefix}})
    add({"ibn:input": {"target": prefix}})
    return bodies


def discover_tasa_hsi_svlans(
    location_prefix: str,
    *,
    access_id: str | None = None,
) -> tuple[list[str], str | None, dict[str, Any]]:
    """
    Busca intents ``tasa-composite`` del ONT en NBI TASA y devuelve SVLAN(s) del target HSI.

    No requiere CVLAN (solo aplica al alta). Si no hay servicios, devuelve lista vacía.
    """
    prefix = (location_prefix or "").strip()
    debug: dict[str, Any] = {"prefix": prefix, "search": [], "list_get": []}
    if not prefix:
        return [], None, debug
    auth = _tasa_auth_headers()
    if not auth:
        return [], "No se pudo autenticar en TASA para detectar SVLAN", debug
    headers, _token = auth
    bases = _tasa_rest_bases()
    if not bases:
        return [], "NBI TASA no configurado", debug
    data_base, ops_base = bases
    found_intents: list[dict[str, Any]] = []
    deep_hits: list[str] = []
    search_timeout = get_altiplano_tasa_discovery_search_timeout_s()
    debug["search_timeout_s"] = search_timeout

    search_url = f"{ops_base.rstrip('/')}/ibn:search-intents?history=false"
    for body in _tasa_search_intents_bodies(prefix, access_id):
        if "ibn:search-intents" in body:
            attempt = {"body": "ibn:search-intents (GUI)"}
        else:
            attempt = {"body_keys": sorted((body.get("ibn:input") or {}).keys())}
        try:
            res = requests.post(
                search_url,
                headers=headers,
                json=body,
                verify=False,
                timeout=search_timeout,
            )
        except requests.RequestException as exc:
            attempt["error"] = str(exc)[:240]
            debug["search"].append(attempt)
            logger.warning("search-intents TASA (%s): %s", prefix, exc)
            continue
        attempt["status_code"] = res.status_code
        data = _json_loads_altiplano_http_response(res)
        if res.status_code != 200:
            attempt["note"] = "non-200"
            debug["search"].append(attempt)
            continue
        if not isinstance(data, dict):
            attempt["note"] = "sin JSON"
            debug["search"].append(attempt)
            continue
        rows = _extract_intent_list_from_search_intents_response(data)
        attempt["rows"] = len(rows)
        for row in rows:
            if str(row.get("intent-type") or "").strip().lower() == "tasa-composite":
                found_intents.append(row)
        scan = extract_hsi_svlans_deep(data, prefix)
        if scan:
            deep_hits = _merge_unique_svlans(deep_hits, scan)
        attempt["deep_svlans"] = len(scan)
        debug["search"].append(attempt)
        if deep_hits or found_intents:
            break

    if not deep_hits and not found_intents and get_altiplano_tasa_discovery_wide_list_enabled():
        list_timeout = get_altiplano_tasa_discovery_wide_list_timeout_s()
        debug["wide_list_enabled"] = True
        debug["wide_list_timeout_s"] = list_timeout
        for rel in get_altiplano_tasa_intent_restconf_paths():
            for params in _TASA_WIDE_LIST_PARAMS:
                url = f"{data_base}/{rel}"
                attempt = {"path": rel, "params": params or None}
                try:
                    res = requests.get(
                        url,
                        headers=headers,
                        params=params or None,
                        verify=False,
                        timeout=list_timeout,
                    )
                except requests.RequestException as exc:
                    attempt["error"] = str(exc)[:240]
                    debug["list_get"].append(attempt)
                    logger.warning("GET %s TASA (wide list): %s", rel, exc)
                    continue
                attempt["status_code"] = res.status_code
                if res.status_code != 200:
                    debug["list_get"].append(attempt)
                    continue
                payload = _json_loads_altiplano_http_response(res)
                if not isinstance(payload, dict):
                    debug["list_get"].append(attempt)
                    continue
                payload = _unwrap_restconf_data_layer(payload)
                batch: list[dict[str, Any]] = []
                _collect_tasa_composite_intents(payload, batch)
                found_intents.extend(batch)
                scan = extract_hsi_svlans_deep(payload, prefix)
                attempt["deep_svlans"] = len(scan)
                debug["list_get"].append(attempt)
                if scan:
                    deep_hits = _merge_unique_svlans(deep_hits, scan)
                    break
            if deep_hits:
                break
    else:
        debug["wide_list_enabled"] = False

    svlans = _merge_unique_svlans(
        _svlans_from_tasa_composite_intents(found_intents, prefix),
        deep_hits,
    )
    debug["svlans"] = svlans
    return svlans, None, debug


def _run_tasa_vno_unconfigure_steps(
    variables: dict[str, str],
    *,
    access_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Delete Services (SVLAN auto-detectado en TASA) y Delete ONT. Devuelve (pasos, error_out)."""
    steps: list[dict[str, Any]] = []
    location_prefix = (
        f"{variables.get('Device Name', '')}-{variables.get('LT', '')}-"
        f"{variables.get('PON', '')}-{variables.get('ONT', '')}"
    )

    discovered, disc_note, disc_dbg = discover_tasa_hsi_svlans(
        location_prefix,
        access_id=access_id,
    )
    svlans_to_try = discovered
    msg_parts = [
        f"Servicios HSI: {', '.join(discovered) if discovered else 'ninguno detectado'}",
    ]
    if disc_note:
        msg_parts.append(disc_note)
    steps.append(
        {
            "phase": "vno",
            "label": "Detectar servicio HSI (TASA)",
            "ok": bool(discovered) or not disc_note,
            "skipped": not discovered and not disc_note,
            "message": ". ".join(msg_parts),
            "discovery": disc_dbg,
        }
    )

    if svlans_to_try:
        for idx, sv in enumerate(svlans_to_try, start=1):
            vars_svc = dict(variables)
            vars_svc["SVLAN"] = sv
            label = "Delete Services"
            if len(svlans_to_try) > 1:
                label = f"Delete Services (SVLAN {sv})"
            r_svc = execute_tasa_postman_api(
                TASA_DELETE_SERVICES_API_ID,
                vars_svc,
                allow_absent=True,
            )
            steps.append(
                {
                    "phase": "vno",
                    "label": label,
                    "api_id": TASA_DELETE_SERVICES_API_ID,
                    **{k: r_svc.get(k) for k in ("ok", "message", "status_code", "skipped")},
                }
            )
            if not r_svc.get("ok"):
                return steps, {
                    "ok": False,
                    "message": r_svc.get("message") or f"Falló Delete Services (SVLAN {sv})",
                    "vno_steps": steps,
                }
    else:
        steps.append(
            {
                "phase": "vno",
                "label": "Delete Services",
                "api_id": TASA_DELETE_SERVICES_API_ID,
                "ok": True,
                "skipped": True,
                "message": (
                    "Sin servicio HSI en TASA para este ONT (o ya borrado). "
                    "Se continúa con Delete ONT."
                ),
            }
        )

    r_ont = execute_tasa_postman_api(
        TASA_DELETE_ONT_API_ID,
        variables,
        allow_absent=True,
    )
    steps.append(
        {
            "phase": "vno",
            "label": "Delete ONT",
            "api_id": TASA_DELETE_ONT_API_ID,
            **{k: r_ont.get(k) for k in ("ok", "message", "status_code", "skipped")},
        }
    )
    if not r_ont.get("ok"):
        return steps, {
            "ok": False,
            "message": r_ont.get("message") or "Falló Delete ONT en TASA",
            "vno_steps": steps,
        }
    return steps, None


def borrar_inp_con_cascada_vno(
    sess_token: str,
    device_name: str,
    by_id: str,
    *,
    svlan: str | None = None,
) -> dict[str, Any]:
    """
    1) VNO (p. ej. TASA): Delete Services + Delete ONT según operador detectado.
    2) INP: borrar intent ont-connection.
    """
    ctx = resolve_borrado_cascade_context(device_name, by_id, sess_token=sess_token)
    if not ctx.get("ok"):
        return ctx

    vno_steps: list[dict[str, Any]] = []
    operator = ctx.get("operator")
    vno_code = ctx.get("vno_code")
    vno_steps.append(
        {
            "phase": "vno",
            "label": "Detectar VNO",
            "ok": True,
            "message": (
                f"Operador {operator}"
                + (f" (código VNO {vno_code})" if vno_code is not None else "")
                + (
                    f" — target INP {(ctx.get('inp_vno_resolution') or {}).get('inp_target')}"
                    if (ctx.get("inp_vno_resolution") or {}).get("inp_target")
                    else ""
                )
            ),
        }
    )

    if operator == "TASA":
        vno_steps_tasa, err = _run_tasa_vno_unconfigure_steps(
            ctx["vno_variables"],
            access_id=ctx.get("access_id"),
        )
        vno_steps.extend(vno_steps_tasa)
        if err:
            err["vno_steps"] = vno_steps
            if ctx.get("inventory_resolution"):
                err["inventory_resolution"] = ctx["inventory_resolution"]
            return err
    elif operator:
        vno_steps.append(
            {
                "phase": "vno",
                "label": f"VNO {operator}",
                "ok": True,
                "skipped": True,
                "message": f"Cascada VNO automática no implementada para {operator}; solo INP.",
            }
        )
    else:
        vno_steps.append(
            {
                "phase": "vno",
                "label": "VNO",
                "ok": True,
                "skipped": True,
                "message": "VNO no identificado en el target; solo borrado INP.",
            }
        )

    inp_out = borrar_intent_ont_connection_inp(
        sess_token,
        device_prefix=ctx.get("inp_device_prefix"),
        access_id=ctx.get("access_id"),
        intent_uuid=None,
    )
    steps = list(vno_steps)
    steps.append(
        {
            "phase": "inp",
            "label": "Delete ONT Connection (INP)",
            "ok": bool(inp_out.get("ok")),
            "message": inp_out.get("message"),
            "target": inp_out.get("target"),
        }
    )

    out: dict[str, Any] = {
        "ok": bool(inp_out.get("ok")),
        "message": inp_out.get("message"),
        "target": inp_out.get("target"),
        "vno_steps": steps,
        "cascade": True,
    }
    if ctx.get("inventory_resolution"):
        out["inventory_resolution"] = ctx["inventory_resolution"]
    for k in ("matches", "access_id"):
        if k in inp_out:
            out[k] = inp_out[k]
    if not inp_out.get("ok"):
        out["message"] = (
            f"Pasos VNO completados; falló borrado INP: {inp_out.get('message') or 'error'}"
        )
    elif operator == "TASA":
        out["message"] = (
            f"Borrado en cascada ({operator}): servicios HSI → ONT → ONT Connection (INP)."
        )
    elif operator:
        out["message"] = (
            f"Borrado INP completado (VNO {operator}: sin cascada automática en NBI operador)."
        )
    return out
