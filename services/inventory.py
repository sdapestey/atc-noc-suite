"""Consultas de inventario (índice: ID, CTO, rama)."""
from collections import defaultdict
from itertools import groupby

from db import db_cursor
from queries import QUERIES

from altiplano import obtener_potencias_por_cto

from .domain import (
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
    calcular_ne,
    nombre_operador,
    region_desde_rama,
)


def consultar_access_id_estructura(access_id):
    with db_cursor() as cur:
        cur.execute(QUERIES["access_id_topologia"], (access_id,))
        row = cur.fetchone()

    if not row:
        return None

    aid, status, cto, rama, obj_raw, obj_ui, op_id = row

    return {
        "AID": aid,
        "OPERADOR": nombre_operador(op_id),
        "Status": status,
        "CTO": cto,
        "RAMA": rama,
        "ONT": obj_ui,
        "TX": None,
        "RX": None,
    }


def consultar_access_id_potencias(access_id):
    base = consultar_access_id_estructura(access_id)
    if not base:
        return {"AID": access_id, "TX": None, "RX": None}

    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_cto"], (base["CTO"],))
        rows = cur.fetchall()

    if not rows:
        return {"AID": access_id, "TX": None, "RX": None}

    ne = calcular_ne(rows[0][4])
    onts = [(str(r[0]), r[4], r[6]) for r in rows if r[4]]
    potencias = obtener_potencias_por_cto(ne, onts)

    tx, rx = potencias.get(str(access_id), (None, None))
    return {"AID": access_id, "TX": tx, "RX": rx}


def consultar_cto_estructura(cto):
    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_cto"], (cto,))
        rows = cur.fetchall()

    out = []
    for r in rows:
        rama_val = r[3]
        if rama_val:
            reg = region_desde_rama(rama_val)
            principal = SITIO_PRINCIPAL_POR_REGION.get(reg, SITIO_PRINCIPAL_DEFAULT)
        else:
            principal = "—"
        out.append({
            "AID": str(r[0]),
            "OPERADOR": nombre_operador(r[6]),
            "RAMA": rama_val,
            "PRINCIPAL": principal,
            "ONT": r[5],
            "STATUS": r[1],
            "TX": None,
            "RX": None,
        })
    return out


def _potencias_desde_filas_ont_cto(rows):
    """Filas con la misma forma que `onts_por_cto` / `onts_por_rama`."""
    if not rows:
        return []
    ne = calcular_ne(rows[0][4])
    onts = [(str(r[0]), r[4], r[6]) for r in rows if r[4]]
    potencias = obtener_potencias_por_cto(ne, onts)
    return [
        {
            "AID": str(r[0]),
            "TX": potencias.get(str(r[0]), (None, None))[0],
            "RX": potencias.get(str(r[0]), (None, None))[1],
        }
        for r in rows
    ]


def consultar_cto_potencias(cto):
    if cto is None or not str(cto).strip():
        return []

    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_cto"], (cto,))
        rows = cur.fetchall()

    return _potencias_desde_filas_ont_cto(rows)


def consultar_rama_estructura(rama):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT f.access_id, f.status, f.location_description,
                   s.object_name, REPLACE(s.object_name,':1-1',''),
                   o.invocator_system
            FROM cm.inventory_fat_occupation f
            JOIN altiplano.serial s ON s.access_id=f.access_id
            JOIN cm.inventory_olt_occupation o ON o.access_id=f.access_id
            WHERE f.path_atc=%s AND f.status='IN SERVICE'
            """,
            (rama,),
        )
        rows = cur.fetchall()

    data = defaultdict(list)
    for r in rows:
        data[r[2]].append({
            "AID": str(r[0]),
            "OPERADOR": nombre_operador(r[5]),
            "ONT": r[4],
            "STATUS": r[1],
            "TX": None,
            "RX": None,
        })
    return data


def consultar_rama_potencias(rama):
    if rama is None or not str(rama).strip():
        return []

    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_rama"], (str(rama).strip(),))
        rows = cur.fetchall()

    if not rows:
        return []

    resultado = []
    for _cto, group in groupby(rows, key=lambda r: r[2]):
        resultado.extend(_potencias_desde_filas_ont_cto(list(group)))
    return resultado
