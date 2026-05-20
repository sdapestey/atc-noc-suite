import json
import re
from pathlib import Path

path = Path(r"c:\Users\Sebastian\Downloads\10.200.4.101.har")
har = json.loads(path.read_text(encoding="utf-8", errors="replace"))
for e in har["log"]["entries"]:
    url = e["request"]["url"]
    if "ema/entity" not in url or "ONT" not in url:
        continue
    resp = (e["response"].get("content") or {}).get("text") or ""
    if "extraAttributes" not in resp:
        continue
    text = resp
    if text.startswith(")]}',"):
        text = text[5:].lstrip()
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        continue
    ea = d.get("extraAttributes") or {}
    if not isinstance(ea, dict):
        continue
    print("URL:", url[:100])
    keys = sorted(ea.keys())
    for k in keys:
        if re.search(r"oper|admin|health|alarm|state|lock", k, re.I):
            print(" ", k, "=>", str(ea[k])[:80])
    print("---")
    break
