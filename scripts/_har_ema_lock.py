import json
from pathlib import Path

p = Path(r"c:\Users\Sebastian\Downloads\10.200.4.101.har")
har = json.loads(p.read_text(encoding="utf-8", errors="replace"))

for e in har["log"]["entries"]:
    post = (e["request"].get("postData") or {}).get("text") or ""
    if "adminStatus" not in post:
        continue
    print("===", e["request"]["method"], e["request"]["url"])
    print("POST", post)
    for h in e["request"]["headers"]:
        n = h.get("name", "").lower()
        if n in ("content-type", "accept", "authorization"):
            print(f"  {h['name']}: {h['value'][:80]}...")
    print("status", e["response"]["status"])
    resp = (e["response"].get("content") or {}).get("text") or ""
    print("resp", resp[:500])
    print()
