import json
from pathlib import Path

path = Path(r"c:\Users\Sebastian\Downloads\10.200.4.101.har")
har = json.loads(path.read_text(encoding="utf-8", errors="replace"))

for e in har["log"]["entries"]:
    url = e["request"]["url"]
    if "allDashboards" not in url:
        continue
    resp = (e["response"].get("content") or {}).get("text") or ""
    if not resp:
        continue
    t = resp[5:].lstrip() if resp.startswith(")]}',") else resp
    d = json.loads(t)
    print(json.dumps(d, indent=2)[:6000])
    break
