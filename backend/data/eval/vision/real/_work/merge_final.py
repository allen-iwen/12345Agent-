"""Merge all candidate metadata files and keep only the final titles."""
import json
import os
import sys

W = os.path.dirname(os.path.abspath(__file__))
merged = {}
for name in ("candidates.json", "candidates2.json", "candidates3.json",
             "candidates4.json", "candidates5.json"):
    p = os.path.join(W, name)
    if not os.path.exists(p):
        continue
    with open(p, encoding="utf-8") as f:
        merged.update(json.load(f))

with open(os.path.join(W, "final_titles.json"), encoding="utf-8") as f:
    wanted = json.load(f)

out = {}
missing = []
for t in wanted:
    if t in merged:
        out[t] = merged[t]
    else:
        missing.append(t)

with open(os.path.join(W, "final_meta.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print("merged pool:", len(merged))
print("final:", len(out))
for m in missing:
    print("MISSING:", m)
for t, r in out.items():
    print("-", t)
    print("   lic:", r["license"], "|", r["license_url"])
    print("   author:", r["author"][:110])
    print("   src:", r["source_url"])
