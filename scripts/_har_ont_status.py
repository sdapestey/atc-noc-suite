import json
from pathlib import Path

path = Path(r"c:\Users\Sebastian\Downloads\10.200.4.101.har")
har = json.loads(path.read_text(encoding="utf-8", errors="replace"))

def parse_text(t):
    if not t:
        return None
    if t.startswith(")]}',"):
        t = t[5:].lstrip()
    return json.loads(t)

targets = [
    "allDashboards",
    "fetchDeviceAttributes=true&isChild=false&isOne=true",
    "7-1-5_GPON/ONT",
]

for e in har["log"]["entries"]:
    url = e["request"]["url"]
    if "ema/entity" not in url:
        continue
    if not any(t in url for t in targets):
        continue
    resp = (e["response"].get("content") or {}).get("text") or ""
    if "operationState" not in resp and "health" not in resp.lower() and "admin" not in resp.lower():
        continue
    print("===", url[:120])
    try:
        d = parse_text(resp)
    except json.JSONDecodeError:
        print("parse fail")
        continue
    s = json.dumps(d, indent=2)[:4000]
    print(s)
    print()
