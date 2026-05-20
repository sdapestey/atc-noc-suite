import json
from pathlib import Path

path = Path(r"c:\Users\Sebastian\Downloads\10.200.4.101.har")
har = json.loads(path.read_text(encoding="utf-8", errors="replace"))

for e in har["log"]["entries"]:
    url = e["request"]["url"]
    if "7-1-5_GPON?" not in url:
        continue
    resp = (e["response"].get("content") or {}).get("text") or ""
    if not resp:
        continue
    t = resp[5:].lstrip() if resp.startswith(")]}',") else resp
    d = json.loads(t)
    qs = url.split("?", 1)[-1]
    print(qs[:80])
    print("  operationState", d.get("operationState"))
    print("  adminStatus", d.get("adminStatus"))
    arn = d.get("alarmResourceNames") or []
    print("  alarms", len(arn) if isinstance(arn, list) else arn)
    print()
