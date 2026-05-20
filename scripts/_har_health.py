import json
from pathlib import Path

path = Path(r"c:\Users\Sebastian\Downloads\10.200.4.101.har")
har = json.loads(path.read_text(encoding="utf-8", errors="replace"))

for e in har["log"]["entries"]:
    url = e["request"]["url"]
    low = url.lower()
    if "health" in low and ("ema" in low or "ibn" in low or "intent" in low):
        print(url[:150])
        resp = (e["response"].get("content") or {}).get("text") or ""
        if resp:
            t = resp[5:].lstrip() if resp.startswith(")]}',") else resp
            print(t[:500])
        print("---")

for e in har["log"]["entries"]:
    if "7-1-5_GPON/parent" in e["request"]["url"]:
        resp = (e["response"].get("content") or {}).get("text") or ""
        t = resp[5:].lstrip() if resp.startswith(")]}',") else resp
        print("PARENT:", json.dumps(json.loads(t), indent=2)[:3000])
