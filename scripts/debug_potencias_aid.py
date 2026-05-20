#!/usr/bin/env python3
"""
Diagnóstico TX/RX Altiplano para un Access ID.

Uso (desde la raíz del repo, con .env cargado):
  python scripts/debug_potencias_aid.py 1058443222
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.inventory import (  # noqa: E402
    _fetch_row_bajada_inventario_detalle,
    consultar_access_id_estructura,
    consultar_access_id_potencias,
)
from db import db_cursor  # noqa: E402
from altiplano import (  # noqa: E402
    _ema_potencias_url,
    _fetch_ont_telemetry_live,
    _ne_from_object_name_raw,
    _power_auth_contexts,
    _restconf_potencias_url,
    normalizar_object_name,
)


def main() -> int:
    aid = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not aid:
        print("Uso: python scripts/debug_potencias_aid.py <ACCESS_ID>")
        return 2

    print(f"=== Access ID: {aid} ===\n")

    base = consultar_access_id_estructura(aid)
    print("Inventario activo:", json.dumps(base, ensure_ascii=False, default=str) if base else "(no)")

    with db_cursor() as cur:
        row = _fetch_row_bajada_inventario_detalle(cur, aid)
    if row:
        row_aid, op_id, *_rest, obj_raw, path_atc, fat_status, sn = (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            row[8],
            row[9],
        )
        print(
            "aux.bajada_inventario:",
            {
                "access_id": row_aid,
                "operator_id": op_id,
                "object_name": obj_raw,
                "path_atc": path_atc,
                "fat_status": fat_status,
                "sn": sn,
            },
        )
    else:
        print("aux.bajada_inventario: (sin fila)")

    obj = str((row and row[6]) or (base and "") or "").strip()
    op_id = (row and row[1]) if row else None
    if base and not obj:
        print("\n(object_name solo en inventario activo — revisar consulta CTO)")

    if obj:
        ne = _ne_from_object_name_raw(obj)
        print(f"\nobject_name normalizado: {normalizar_object_name(obj)}")
        print(f"NE: {ne}")
        contexts = _power_auth_contexts(op_id)
        print(f"\nContextos auth ({len(contexts)}):")
        for vno, auth_url, user, _pwd in contexts:
            print(f"  - vno={vno} user={user} auth_url={auth_url}")
            if ne:
                host = auth_url.split("/")[2]
                print(f"    RESTCONF: {_restconf_potencias_url(host, vno, ne, obj)}")
                print(f"    EMA:      {_ema_potencias_url(host, vno, ne, obj)}")

        if ne:
            telem = _fetch_ont_telemetry_live(aid, obj, op_id, ne)
            print(f"\n_fetch_ont_telemetry_live -> {telem}")

    out = consultar_access_id_potencias(aid)
    print(f"\nconsultar_access_id_potencias -> {json.dumps(out, ensure_ascii=False)}")
    return 0 if out.get("TX") is not None or out.get("RX") is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
