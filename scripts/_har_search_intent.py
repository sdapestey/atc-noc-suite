import json
from pathlib import Path

path = Path(r"c:\Users\Sebastian\Downloads\10.200.4.101.har")
har = json.loads(path.read_text(encoding="utf-8", errors="replace"))

for e in har["log"]["entries"]:
    if "search-intents" not in e["request"]["url"]:
        continue
    req = (e["request"].get("postData") or {}).get("text") or ""
    if "1058443222" not in req:
        continue
    resp = (e["response"].get("content") or {}).get("text") or ""
    if not resp:
        continue
    t = resp[5:].lstrip() if resp.startswith(")]}',") else resp
    print(json.dumps(json.loads(t), indent=2)[:3000])
    break
