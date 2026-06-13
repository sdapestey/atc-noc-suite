"""Cortes de rama: alarmas PON masivas (Dying Gasp / LOSi-LOBi) en Altiplano INP."""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from zoneinfo import ZoneInfo

from altiplano import _normalize_corte_pon_estado, obtener_alarmas_corte_pon
from config import get_dashboard_historico_cache_seconds
from db import db_cursor
from queries import QUERIES

from .dashboard_cache import get_cached_historico_potencias
from .domain import (
    OPERADORES_CONSULTA_ORDEN,
    canonical_operador_consulta,
    nombre_operador,
    principal_y_sitio_desde_olt,
    region_desde_rama,
    sort_operadores_consulta,
)

_PON_KEY_FROM_OBJ_DASH_RE = re.compile(r"^(BA_OLTA_[A-Za-z0-9_]+)-(\d+)-(\d+)-")
_PON_KEY_FROM_OBJ_COLON_RE = re.compile(r"^(BA_OLTA_[A-Za-z0-9_]+):1-1-(\d+)-(\d+)-")
_PON_KEY_RE = re.compile(r"^(BA_OLTA_[A-Za-z0-9_]+)-(\d+)-(\d+)$")

CORTES_RAMA_SORTS = ("reciente", "antiguo", "clientes")
CORTES_RAMA_IMPACTOS = ("MODERADO", "URGENTE", "EMERGENCIA")

_TZ_NOC = ZoneInfo("America/Argentina/Buenos_Aires")

_CAUSA_LABELS = {
    "DYING_GASP": "Dying Gasp",
    "LOSI_LOBI": "LOSi / LOBi",
    "OTRO": "Otro",
}

_CAUSA_TIPO_EVENTO = {
    "LOSI_LOBI": "fibra",
    "DYING_GASP": "luz",
    "OTRO": "otro",
}

_TIPO_EVENTO_LABELS = {
    "fibra": "Corte de fibra",
    "luz": "Corte de luz",
    "otro": "Otro",
}

_IMPACTO_LABELS = {
    "MODERADO": "Moderado",
    "URGENTE": "Urgente",
    "EMERGENCIA": "Emergencia",
}

_IMPACTO_RANK = {"MODERADO": 1, "URGENTE": 2, "EMERGENCIA": 3}
_TIPO_EVENTO_RANK = {"fibra": 0, "luz": 1, "otro": 2}

# Ventana ART para considerar cortes simultáneos (misma OLT, p. ej. 08:34 y 08:35).
_CORTE_SIMULTANEO_VENTANA_MIN = 2


def _pon_patterns_for_key(pon_key: str) -> tuple[str, str] | None:
    m = _PON_KEY_RE.match(str(pon_key or "").strip())
    if not m:
        return None
    olt, lt, pon = m.group(1), m.group(2), m.group(3)
    dash = f"{olt}-{lt}-{pon}-%"
    colon = f"{olt}:1-1-{lt}-{pon}-%"
    return dash, colon


def _pon_patterns_for_keys(pon_keys: list[str]) -> tuple[list[str], set[str]]:
    obj_patterns: list[str] = []
    valid_keys: set[str] = set()
    for pk in pon_keys:
        pats = _pon_patterns_for_key(pk)
        if not pats:
            continue
        dash, colon = pats
        obj_patterns.append(dash)
        obj_patterns.append(colon)
        valid_keys.add(pk)
    return obj_patterns, valid_keys


def _pon_key_from_object_name(obj_norm: str) -> str | None:
    s = str(obj_norm or "").strip()
    for pattern in (_PON_KEY_FROM_OBJ_DASH_RE, _PON_KEY_FROM_OBJ_COLON_RE):
        m = pattern.match(s)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _vno_label(invocator_system) -> str | None:
    raw = nombre_operador(invocator_system)
    return canonical_operador_consulta(raw) or raw or None


def _rama_sort_key(path: str) -> tuple:
    u = str(path or "").upper()
    kind = 0 if "-RATC-" in u else 1 if "-FATC-" in u else 2
    return (kind, path.lower())


def _merge_ramas_display(ratcs: set[str], fatcs: set[str]) -> list[str]:
    ratc_list = sorted(ratcs, key=str.lower)
    if ratc_list:
        return ratc_list
    return sorted(fatcs, key=str.lower)


def _batch_inventario_por_pon_keys(pon_keys: list[str]) -> dict[str, dict]:
    """Inventario IN SERVICE por ``pon_key``: RAMAs, clientes y conteo por VNO."""
    keys = sorted({str(k or "").strip() for k in pon_keys if str(k or "").strip()})
    obj_patterns, valid_keys = _pon_patterns_for_keys(keys)
    if not obj_patterns:
        return {}

    agg: dict[str, dict] = defaultdict(
        lambda: {
            "ratcs": set(),
            "fatcs": set(),
            "paths": set(),
            "ont_total": 0,
            "vnos": defaultdict(int),
        }
    )
    with db_cursor() as cur:
        cur.execute(
            QUERIES["cortes_rama_inventario_por_pon"],
            (obj_patterns,),
        )
        for obj_norm, rama, invocator in cur.fetchall():
            pk = _pon_key_from_object_name(str(obj_norm or ""))
            if not pk or pk not in valid_keys:
                continue
            bucket = agg[pk]
            bucket["ont_total"] += 1
            path = str(rama or "").strip()
            if path:
                bucket["paths"].add(path)
            u = path.upper()
            if "-RATC-" in u:
                bucket["ratcs"].add(path)
            elif "-FATC-" in u:
                bucket["fatcs"].add(path)
            vno = _vno_label(invocator)
            if vno:
                bucket["vnos"][vno] += 1

    out: dict[str, dict] = {}
    for pk, bucket in agg.items():
        ratcs = bucket["ratcs"]
        fatcs = bucket["fatcs"]
        vnos_map = dict(bucket["vnos"])
        vno_list = [
            {"vno": vno, "count": vnos_map[vno]}
            for vno in sort_operadores_consulta(vnos_map.keys())
        ]
        ramas = _merge_ramas_display(ratcs, fatcs)
        if not ramas:
            ramas = sorted(bucket["paths"], key=_rama_sort_key)
        out[pk] = {
            "ramas": ramas,
            "ramas_ratc": sorted(ratcs, key=str.lower),
            "ramas_fatc": sorted(fatcs, key=str.lower),
            "ramas_count": len(ramas),
            "ont_total": int(bucket["ont_total"]),
            "vnos": vnos_map,
            "vno_list": vno_list,
        }
    return out


def _raised_as_utc_dt(iso: str | None) -> datetime | None:
    s = str(iso or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        elif s.endswith("+0000"):
            s = s[:-5] + "+00:00"
        dt = datetime.fromisoformat(s.replace(".000", ""))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _raised_local_date(iso: str | None) -> date | None:
    dt = _raised_as_utc_dt(iso)
    if not dt:
        return None
    return dt.astimezone(_TZ_NOC).date()


def _raised_local_minute_label(iso: str | None) -> str:
    dt = _raised_as_utc_dt(iso)
    if not dt:
        return ""
    local = dt.astimezone(_TZ_NOC)
    return local.strftime("%Y-%m-%d %H:%M")


def _ventana_corte_simultaneo(
    iso: str | None, *, ventana_min: int = _CORTE_SIMULTANEO_VENTANA_MIN
) -> str:
    """Inicio de ventana ART (p. ej. 08:34 agrupa 08:34–08:35)."""
    dt = _raised_as_utc_dt(iso)
    if not dt:
        return ""
    local = dt.astimezone(_TZ_NOC)
    bucket_min = (local.minute // ventana_min) * ventana_min
    inicio = local.replace(minute=bucket_min, second=0, microsecond=0)
    return inicio.strftime("%Y-%m-%d %H:%M")


def _cluster_evento_simultaneo_key(item: dict) -> str:
    """Sitio principal + ventana ART + causa (varias OLT del mismo sitio suman)."""
    ventana = _ventana_corte_simultaneo(item.get("raised"))
    causa = str(item.get("causa") or "OTRO").strip().upper()
    sitio = str(item.get("principal") or "").strip()
    scope = sitio or str(item.get("olt") or "").strip()
    if not scope or not ventana:
        return ""
    return f"{scope}|{ventana}|{causa}"


def _tipo_evento_desde_causa(causa: str | None) -> str:
    return _CAUSA_TIPO_EVENTO.get(str(causa or "OTRO").strip().upper(), "otro")


def _parse_fecha_filtro(fecha: str | None) -> date | None:
    raw = (fecha or "").strip().lower()
    if not raw:
        return None
    hoy = datetime.now(_TZ_NOC).date()
    if raw in ("hoy", "today"):
        return hoy
    if raw in ("ayer", "yesterday"):
        return hoy - timedelta(days=1)
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _clasificar_impacto(ont_total: int | str | None) -> str:
    n = max(0, int(ont_total or 0))
    if n >= 250:
        return "EMERGENCIA"
    if n >= 16:
        return "URGENTE"
    return "MODERADO"


def _impacto_evento(clientes_total: int) -> str:
    return _clasificar_impacto(clientes_total)


def _enrich_item_impacto(item: dict) -> dict:
    impacto_pon = _clasificar_impacto(item.get("ont_total"))
    item["impacto_pon"] = impacto_pon
    item["impacto_pon_label"] = _IMPACTO_LABELS.get(impacto_pon, impacto_pon)
    item["impacto"] = impacto_pon
    item["impacto_label"] = _IMPACTO_LABELS.get(impacto_pon, impacto_pon)
    item["evento_simultaneo"] = False
    item["raised_local"] = _raised_local_minute_label(item.get("raised"))
    return item


def _build_clusters_simultaneos(items: list[dict]) -> dict[str, dict]:
    buckets: dict[str, dict] = {}
    for item in items:
        key = _cluster_evento_simultaneo_key(item)
        if not key:
            continue
        ventana = _ventana_corte_simultaneo(item.get("raised"))
        causa = str(item.get("causa") or "OTRO").strip().upper()
        bucket = buckets.setdefault(
            key,
            {
                "cluster_key": key,
                "ventana": ventana,
                "causa": causa,
                "principal": "",
                "olts": set(),
                "cortes": 0,
                "clientes": 0,
                "pons": [],
            },
        )
        bucket["cortes"] += 1
        bucket["clientes"] += int(item.get("ont_total") or 0)
        pk = str(item.get("pon_key") or "")
        if pk:
            bucket["pons"].append(pk)
        olt = str(item.get("olt") or "").strip()
        if olt:
            bucket["olts"].add(olt)
        principal = str(item.get("principal") or "").strip()
        if principal and not bucket["principal"]:
            bucket["principal"] = principal
    for bucket in buckets.values():
        imp = _impacto_evento(bucket["clientes"])
        bucket["impacto"] = imp
        bucket["impacto_label"] = _IMPACTO_LABELS.get(imp, imp)
    return buckets


def _aplicar_impacto_cortes_simultaneos(items: list[dict]) -> list[dict]:
    """Suma clientes de cortes en la misma ventana/sitio para nivel de impacto NOC."""
    clusters = _build_clusters_simultaneos(items)
    multi = {k: v for k, v in clusters.items() if int(v.get("cortes") or 0) >= 2}
    for item in items:
        key = _cluster_evento_simultaneo_key(item)
        cluster = multi.get(key)
        if not cluster:
            item["evento_simultaneo"] = False
            continue
        item["evento_simultaneo"] = True
        item["evento_ventana"] = cluster["ventana"]
        item["evento_cortes"] = int(cluster["cortes"])
        item["evento_clientes"] = int(cluster["clientes"])
        item["evento_impacto"] = cluster["impacto"]
        item["evento_causa"] = cluster.get("causa") or str(item.get("causa") or "OTRO")
        item["evento_tipo"] = _tipo_evento_desde_causa(item["evento_causa"])
        item["impacto"] = cluster["impacto"]
        item["impacto_label"] = cluster["impacto_label"]
    return items


def _compute_totales(items: list[dict]) -> dict:
    totales = {
        "TOTAL": 0,
        "DYING_GASP": 0,
        "LOSI_LOBI": 0,
        "OTRO": 0,
        "PON_UNICOS": 0,
        "RAMAS_IMPACTADAS": 0,
        "CLIENTES_AFECTADOS": 0,
        "SIN_INVENTARIO": 0,
        "MODERADO": 0,
        "URGENTE": 0,
        "EMERGENCIA": 0,
    }
    pon_seen: set[str] = set()
    ramas_impactadas: set[str] = set()
    for item in items:
        causa_code = str(item.get("causa") or "OTRO")
        totales["TOTAL"] += 1
        totales[causa_code] = totales.get(causa_code, 0) + 1
        pk = str(item.get("pon_key") or "")
        if pk:
            pon_seen.add(pk)
        ont_total = int(item.get("ont_total") or 0)
        if not item.get("ramas") and ont_total == 0:
            totales["SIN_INVENTARIO"] += 1
        for r in item.get("ramas") or []:
            ramas_impactadas.add(str(r))
        totales["CLIENTES_AFECTADOS"] += ont_total
        imp = str(item.get("impacto") or _clasificar_impacto(ont_total))
        if imp in totales:
            totales[imp] += 1
    totales["PON_UNICOS"] = len(pon_seen)
    totales["RAMAS_IMPACTADAS"] = len(ramas_impactadas)
    return totales


def _detect_eventos_masivos(items: list[dict]) -> list[dict]:
    """Cortes simultáneos: mismo sitio en ventana ART de 2 minutos."""
    eventos: list[dict] = []
    for bucket in _build_clusters_simultaneos(items).values():
        if int(bucket.get("cortes") or 0) < 2:
            continue
        causa = str(bucket.get("causa") or "OTRO").strip().upper()
        tipo = _tipo_evento_desde_causa(causa)
        olts = sorted(bucket.get("olts") or [])
        eventos.append(
            {
                "minute": bucket["ventana"],
                "ventana": bucket["ventana"],
                "olt": olts[0] if len(olts) == 1 else "",
                "olts": olts,
                "principal": bucket.get("principal") or "",
                "causa": causa,
                "causa_label": _CAUSA_LABELS.get(causa, causa),
                "tipo": tipo,
                "tipo_label": _TIPO_EVENTO_LABELS.get(tipo, "Otro"),
                "cortes": bucket["cortes"],
                "clientes": bucket["clientes"],
                "pon_keys": list(bucket.get("pons") or []),
                "pons": (bucket.get("pons") or [])[:12],
                "impacto": bucket["impacto"],
                "impacto_label": bucket["impacto_label"],
            }
        )
    eventos.sort(
        key=lambda e: (
            _TIPO_EVENTO_RANK.get(str(e.get("tipo")), 9),
            -_IMPACTO_RANK.get(str(e.get("impacto")), 0),
            -int(e.get("clientes") or 0),
            -int(e.get("cortes") or 0),
        )
    )
    return eventos


def _filter_items(
    items: list[dict],
    *,
    causa: str | None = None,
    principal: str | None = None,
    vno: str | None = None,
    q: str | None = None,
    solo_con_rama: bool = False,
    fecha: date | None = None,
    impacto: str | None = None,
) -> list[dict]:
    causa_u = (causa or "").strip().upper()
    principal_u = (principal or "").strip().upper()
    vno_f = (vno or "").strip()
    q_l = (q or "").strip().lower()
    impacto_u = (impacto or "").strip().upper()
    filtered: list[dict] = []
    for item in items:
        if causa_u and causa_u != "ALL" and str(item.get("causa") or "").upper() != causa_u:
            continue
        if principal_u and principal_u != "ALL":
            if str(item.get("principal") or "").upper() != principal_u:
                continue
        if vno_f and vno_f.upper() != "ALL":
            vnos = item.get("vnos") or {}
            if not any(
                canonical_operador_consulta(k) == canonical_operador_consulta(vno_f)
                or k.upper() == vno_f.upper()
                for k in vnos
            ):
                continue
        if solo_con_rama and not item.get("ramas"):
            continue
        if fecha is not None:
            if _raised_local_date(item.get("raised")) != fecha:
                continue
        if impacto_u and impacto_u != "ALL":
            if str(item.get("impacto") or "").upper() != impacto_u:
                continue
        if q_l:
            haystack = " ".join(
                str(item.get(k) or "")
                for k in (
                    "olt",
                    "lt_name",
                    "pon_label",
                    "pon_key",
                    "causa_label",
                    "resource",
                    "text",
                    "main_device",
                )
            ).lower()
            ramas_txt = " ".join(item.get("ramas") or []).lower()
            vno_txt = " ".join((item.get("vnos") or {}).keys()).lower()
            if q_l not in haystack and q_l not in ramas_txt and q_l not in vno_txt:
                continue
        filtered.append(item)
    return filtered


def _raised_sort_ts(iso: str | None) -> float:
    dt = _raised_as_utc_dt(iso)
    return dt.timestamp() if dt else 0.0


def _normalize_sort(sort_by: str | None) -> str:
    s = (sort_by or "reciente").strip().lower()
    return s if s in CORTES_RAMA_SORTS else "reciente"


def _sort_cortes_items(items: list[dict], sort_by: str | None = None) -> list[dict]:
    mode = _normalize_sort(sort_by)
    if mode == "antiguo":
        return sorted(
            items,
            key=lambda r: (_raised_sort_ts(r.get("raised")), str(r.get("pon_key") or "")),
        )
    if mode == "clientes":
        return sorted(
            items,
            key=lambda r: (
                -int(r.get("ont_total") or 0),
                -_raised_sort_ts(r.get("raised")),
                str(r.get("pon_key") or ""),
            ),
        )
    return sorted(
        items,
        key=lambda r: (
            -_raised_sort_ts(r.get("raised")),
            -int(r.get("ont_total") or 0),
            str(r.get("pon_key") or ""),
        ),
    )


def _grupo_raised_ts(g: dict, *, newest: bool = True) -> float:
    rows = g.get("items") or []
    if not rows:
        return 0.0
    ts = [_raised_sort_ts(r.get("raised")) for r in rows]
    return max(ts) if newest else min(ts)


def _sort_grupos_sitio_lt(grupos: list[dict], sort_by: str | None = None) -> list[dict]:
    mode = _normalize_sort(sort_by)
    if mode == "antiguo":
        return sorted(
            grupos,
            key=lambda g: (_grupo_raised_ts(g, newest=False), str(g.get("lt_name") or "")),
        )
    if mode == "clientes":
        return sorted(
            grupos,
            key=lambda g: (-int(g.get("ont_total") or 0), str(g.get("lt_name") or "")),
        )
    return sorted(
        grupos,
        key=lambda g: (
            -_grupo_raised_ts(g, newest=True),
            -int(g.get("ont_total") or 0),
            str(g.get("lt_name") or ""),
        ),
    )


def _build_grupos_sitio_lt(items: list[dict], sort_by: str | None = None) -> list[dict]:
    """Agrupa cortes por sitio principal + LT para vista colapsable en UI."""
    groups: dict[str, dict] = {}
    for item in items:
        principal = str(item.get("principal") or "")
        lt_name = str(item.get("lt_name") or "")
        key = f"{principal}|{lt_name}"
        if key not in groups:
            groups[key] = {
                "principal": principal,
                "lt_name": lt_name,
                "olt": item.get("olt") or "",
                "lt": item.get("lt") or "",
                "cortes": 0,
                "ont_total": 0,
                "losi": 0,
                "dying": 0,
                "ramas": set(),
                "vnos_acc": defaultdict(int),
                "items": [],
            }
        g = groups[key]
        g["cortes"] += 1
        g["ont_total"] += int(item.get("ont_total") or 0)
        causa = str(item.get("causa") or "")
        if causa == "LOSI_LOBI":
            g["losi"] += 1
        elif causa == "DYING_GASP":
            g["dying"] += 1
        for rama in item.get("ramas") or []:
            g["ramas"].add(str(rama))
        for vno, count in (item.get("vnos") or {}).items():
            label = canonical_operador_consulta(vno) or vno
            g["vnos_acc"][label] += int(count or 0)
        g["items"].append(item)

    out: list[dict] = []
    for g in groups.values():
        g["ramas"] = sorted(g.pop("ramas"), key=str.lower)
        g["ramas_count"] = len(g["ramas"])
        vnos_acc = g.pop("vnos_acc")
        g["vno_list"] = [
            {"vno": vno, "count": vnos_acc[vno]}
            for vno in sort_operadores_consulta(vnos_acc.keys())
        ]
        g["items"] = _sort_cortes_items(g["items"], sort_by)
        out.append(g)
    return _sort_grupos_sitio_lt(out, sort_by)


def _totales_vno(items: list[dict]) -> list[dict]:
    acc: dict[str, int] = defaultdict(int)
    for item in items:
        for vno, count in (item.get("vnos") or {}).items():
            label = canonical_operador_consulta(vno) or vno
            acc[label] += int(count or 0)
    return [
        {"vno": vno, "count": acc[vno]}
        for vno in sort_operadores_consulta(acc.keys())
    ]


def _cortes_rama_uncached(
    *,
    causa: str | None = None,
    principal: str | None = None,
    vno: str | None = None,
    q: str | None = None,
    solo_con_rama: bool = False,
    limit: int = 500,
    sort_by: str | None = None,
    fecha: str | None = None,
    impacto: str | None = None,
    estado: str = "activas",
) -> dict:
    estado_norm = _normalize_corte_pon_estado(estado)
    fecha_d = _parse_fecha_filtro(fecha)
    alarmas = obtener_alarmas_corte_pon(estado_norm, raised_on=fecha_d)
    pon_keys = [str(a.get("pon_key") or "") for a in alarmas if a.get("pon_key")]
    inv_by_pon = _batch_inventario_por_pon_keys(pon_keys)

    items: list[dict] = []
    principals: set[str] = set()
    vnos_globales: set[str] = set()

    for al in alarmas:
        pk = str(al.get("pon_key") or "")
        olt = str(al.get("olt") or "")
        sitio_principal, _sitio, _cod = principal_y_sitio_desde_olt(olt)
        principals.add(sitio_principal)
        inv = inv_by_pon.get(pk, {})
        ramas = list(inv.get("ramas") or [])
        vnos = dict(inv.get("vnos") or {})
        vno_list = list(inv.get("vno_list") or [])
        ont_total = int(inv.get("ont_total") or 0)
        for v in vnos:
            vnos_globales.add(v)
        causa_code = str(al.get("causa") or "OTRO")
        items.append(
            _enrich_item_impacto(
                {
                    "causa": causa_code,
                    "causa_label": _CAUSA_LABELS.get(causa_code, causa_code),
                    "severity": al.get("severity") or "",
                    "status": al.get("status") or "",
                    "raised": al.get("raised") or "",
                    "cleared": al.get("cleared") or "",
                    "olt": olt,
                    "lt": str(al.get("lt") or ""),
                    "lt_name": str(al.get("lt_name") or ""),
                    "pon": str(al.get("pon") or ""),
                    "pon_label": str(al.get("pon_label") or ""),
                    "pon_key": pk,
                    "principal": sitio_principal,
                    "region": region_desde_rama(ramas[0]) if ramas else "",
                    "ramas": ramas,
                    "ramas_ratc": list(inv.get("ramas_ratc") or []),
                    "ramas_fatc": list(inv.get("ramas_fatc") or []),
                    "ramas_count": len(ramas),
                    "ont_total": ont_total,
                    "vnos": vnos,
                    "vno_list": vno_list,
                    "sin_inventario": not ramas and ont_total == 0,
                    "resource": al.get("resource") or "",
                    "text": al.get("text") or "",
                    "main_device": al.get("main_device") or olt,
                }
            )
        )

    items = _aplicar_impacto_cortes_simultaneos(items)

    totales_global = _compute_totales(items)
    filtered = _filter_items(
        items,
        causa=causa,
        principal=principal,
        vno=vno,
        q=q,
        solo_con_rama=solo_con_rama,
        fecha=fecha_d,
        impacto=impacto,
    )
    sort_mode = _normalize_sort(sort_by)
    filtered = _sort_cortes_items(filtered, sort_mode)
    limit_val = max(1, min(int(limit or 500), 2000))
    totales = _compute_totales(filtered)
    eventos_masivos = _detect_eventos_masivos(filtered)
    return {
        "ok": True,
        "estado": estado_norm,
        "sort": sort_mode,
        "fecha_filtro": fecha_d.isoformat() if fecha_d else "",
        "items": filtered[:limit_val],
        "grupos": _build_grupos_sitio_lt(filtered, sort_mode),
        "total_filtrado": len(filtered),
        "totales": totales,
        "totales_global": totales_global,
        "eventos_masivos": eventos_masivos,
        "vno_resumen": _totales_vno(filtered),
        "principals": sorted(principals, key=str.lower),
        "vnos": sort_operadores_consulta(vnos_globales),
        "generated_at": datetime.now(_TZ_NOC).strftime("%Y-%m-%d %H:%M:%S"),
    }


def consultar_cortes_rama(
    *,
    causa: str | None = None,
    principal: str | None = None,
    vno: str | None = None,
    q: str | None = None,
    solo_con_rama: bool = False,
    limit: int = 500,
    sort_by: str | None = None,
    fecha: str | None = None,
    impacto: str | None = None,
    estado: str = "activas",
    fresh: bool = False,
) -> dict:
    """Cortes por PON con RAMAs afectadas (Altiplano INP + inventario)."""
    sort_mode = _normalize_sort(sort_by)
    estado_norm = _normalize_corte_pon_estado(estado)
    if fresh:
        return _cortes_rama_uncached(
            causa=causa,
            principal=principal,
            vno=vno,
            q=q,
            solo_con_rama=solo_con_rama,
            limit=limit,
            sort_by=sort_mode,
            fecha=fecha,
            impacto=impacto,
            estado=estado_norm,
        )
    fecha_key = (fecha or "").strip().lower()[:10]
    impacto_key = (impacto or "ALL").strip().upper()
    cache_key = "|".join(
        [
            estado_norm,
            (causa or "ALL").strip().upper(),
            (principal or "ALL").strip().upper(),
            (vno or "ALL").strip().upper(),
            (q or "").strip().lower(),
            "1" if solo_con_rama else "0",
            str(max(1, min(int(limit or 500), 2000))),
            sort_mode,
            fecha_key or "ALL",
            impacto_key,
        ]
    )
    return get_cached_historico_potencias(
        get_dashboard_historico_cache_seconds(),
        f"cortes_rama|v8|{cache_key}",
        lambda: _cortes_rama_uncached(
            causa=causa,
            principal=principal,
            vno=vno,
            q=q,
            solo_con_rama=solo_con_rama,
            limit=limit,
            sort_by=sort_mode,
            fecha=fecha,
            impacto=impacto,
            estado=estado_norm,
        ),
    )


def export_csv_cortes_rama(
    *,
    causa: str | None = None,
    principal: str | None = None,
    vno: str | None = None,
    q: str | None = None,
    solo_con_rama: bool = False,
    limit: int = 2000,
    sort_by: str | None = None,
    fecha: str | None = None,
    impacto: str | None = None,
    estado: str = "activas",
) -> dict:
    payload = consultar_cortes_rama(
        causa=causa,
        principal=principal,
        vno=vno,
        q=q,
        solo_con_rama=solo_con_rama,
        limit=limit,
        sort_by=sort_by,
        fecha=fecha,
        impacto=impacto,
        estado=estado,
    )
    if not payload.get("ok"):
        return payload

    out = StringIO()
    w = csv.writer(out)
    w.writerow(
        [
            "CAUSA",
            "ESTADO",
            "OLT",
            "LT",
            "PON",
            "PON_KEY",
            "DESDE_UTC",
            "CLEARED_UTC",
            "PRINCIPAL",
            "CLIENTES",
            "IMPACTO",
            "VNO_DESGLOSE",
            "RAMAS",
            "RAMAS_COUNT",
            "SEVERITY",
            "ALARM_RESOURCE",
            "DETALLE",
        ]
    )
    for row in payload.get("items") or []:
        vno_parts = [
            f"{v['vno']}:{v['count']}"
            for v in (row.get("vno_list") or [])
        ]
        w.writerow(
            [
                row.get("causa_label") or row.get("causa") or "",
                row.get("status") or "",
                row.get("olt") or "",
                row.get("lt") or "",
                row.get("pon") or "",
                row.get("pon_key") or "",
                row.get("raised") or "",
                row.get("cleared") or "",
                row.get("principal") or "",
                row.get("ont_total") or 0,
                row.get("impacto_label") or row.get("impacto") or "",
                ";".join(vno_parts),
                ";".join(row.get("ramas") or []),
                row.get("ramas_count") or 0,
                row.get("severity") or "",
                row.get("resource") or "",
                row.get("text") or "",
            ]
        )
    return {**payload, "csv": out.getvalue()}


def _pon_label_from_key(pon_key: str) -> str:
    m = _PON_KEY_RE.match(str(pon_key or "").strip())
    if not m:
        return str(pon_key or "").strip()
    return f"PON {m.group(3)}"


def _format_pon_export_flat_sparse_csv(rows: list[dict[str, str]]) -> list[list[str]]:
    """Mismo layout sparse que ``_formatPonExportFlatSparse`` en ``dashboard-olt.js``."""
    out: list[list[str]] = [["PON", "RAMA", "CTO", "ACCESS ID", "OPERADOR", "ONT"]]
    prev_pon = prev_rama = prev_cto = None
    for row in rows:
        pon = row["pon"]
        rama = row["rama"]
        cto = row["cto"]
        pon_col = pon if pon != prev_pon else ""
        rama_col = rama if pon != prev_pon or rama != prev_rama else ""
        cto_col = cto if pon != prev_pon or rama != prev_rama or cto != prev_cto else ""
        out.append([pon_col, rama_col, cto_col, row["aid"], row["operador"], row["ont"]])
        prev_pon, prev_rama, prev_cto = pon, rama, cto
    return out


def _pon_export_resumen_csv_rows(
    pon_count: int,
    ramas: set[str],
    ctos: set[tuple[str, str]],
    ont_count: int,
    operador_counts: dict[str, int],
) -> list[list[str]]:
    """Pie de resumen alineado con ``_ponExportResumenLines`` en ``dashboard-olt.js``."""
    lines: list[list[str]] = [[], ["RESUMEN:"]]
    lines.append([f"PON: {pon_count}"])
    lines.append([f"RAMAS: {len(ramas)}"])
    lines.append([f"CTO: {len(ctos)}"])
    lines.append([f"ONT: {ont_count}"])
    for op in OPERADORES_CONSULTA_ORDEN:
        n = int(operador_counts.get(op) or 0)
        if n > 0:
            lines.append([f"{op}: {n}"])
    return lines


def export_csv_evento_reporte_pon(
    pon_keys: list[str] | None,
    *,
    principal: str | None = None,
    ventana: str | None = None,
) -> dict:
    """
    Reporte de clientes IN SERVICE por PON (mismo layout que export OLT/LT):
    columnas sparse PON/RAMA/CTO + resumen PON/RAMAS/CTO/ONT/operadores.
    """
    _ = principal, ventana  # reservado para API; el CSV replica solo el export OLT/LT
    keys = sorted({str(k or "").strip() for k in (pon_keys or []) if str(k or "").strip()})
    if not keys:
        return {"ok": False, "message": "Indicá al menos un PON", "status_code": 400}

    obj_patterns, valid_keys = _pon_patterns_for_keys(keys)
    if not obj_patterns:
        return {
            "ok": False,
            "message": "Ningún PON válido para el reporte",
            "status_code": 400,
        }

    rows_data: list[dict[str, str]] = []
    ramas_set: set[str] = set()
    ctos_set: set[tuple[str, str]] = set()
    operador_counts: dict[str, int] = defaultdict(int)

    with db_cursor() as cur:
        cur.execute(QUERIES["cortes_rama_reporte_inventario_pon"], (obj_patterns,))
        for obj_norm, rama, cto, access_id, invocator in cur.fetchall():
            pk = _pon_key_from_object_name(str(obj_norm or ""))
            if not pk or pk not in valid_keys:
                continue
            aid = str(access_id or "").strip()
            if not aid:
                continue
            rama_s = str(rama or "").strip()
            cto_s = str(cto or "").strip()
            op_raw = nombre_operador(invocator) or ""
            op_canon = canonical_operador_consulta(op_raw)
            if op_canon:
                operador_counts[op_canon] += 1
            ramas_set.add(rama_s)
            ctos_set.add((rama_s, cto_s))
            rows_data.append(
                {
                    "pon": _pon_label_from_key(pk),
                    "rama": rama_s,
                    "cto": cto_s,
                    "aid": aid,
                    "operador": op_raw,
                    "ont": str(obj_norm or "").strip() or "—",
                }
            )

    if not rows_data:
        return {
            "ok": False,
            "message": "Sin clientes IN SERVICE en inventario para esos PON",
            "status_code": 404,
        }

    rows_data.sort(key=lambda r: (r["pon"], r["rama"], r["cto"], r["aid"]))

    csv_rows = _format_pon_export_flat_sparse_csv(rows_data)
    csv_rows.extend(
        _pon_export_resumen_csv_rows(
            len(valid_keys),
            ramas_set,
            ctos_set,
            len(rows_data),
            operador_counts,
        )
    )

    out = StringIO()
    w = csv.writer(out, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    for row in csv_rows:
        w.writerow(row)

    stamp = datetime.now(_TZ_NOC).strftime("%Y-%m-%d")
    filename = f"pones_seleccionados_{stamp}.csv"

    return {
        "ok": True,
        "csv": out.getvalue(),
        "filename": filename,
        "row_count": len(rows_data),
        "pon_count": len(valid_keys),
    }
