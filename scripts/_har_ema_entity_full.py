import json
from pathlib import Path

path = Path(r"c:\Users\Sebastian\Downloads\10.200.4.101.har")
har = json.loads(path.read_text(encoding="utf-8", errors="replace"))

for e in har["log"]["entries"]:
    url = e["request"]["url"]
    if "7-1-5_GPON" not in url or "ema/entity" not in url:
        continue
    if "fetchDeviceAttributes=false" not in url and "isOne=true" not in url:
        continue
    resp = (e["response"].get("content") or {}).get("text") or ""
    if not resp:
        continue
    t = resp[5:].lstrip() if resp.startswith(")]}',") else resp
    d = json.loads(t)
    print("URL:", url[80:160])
    for k in sorted(d.keys()):
        print(" top:", k, "=", str(d[k])[:60])
    print()
