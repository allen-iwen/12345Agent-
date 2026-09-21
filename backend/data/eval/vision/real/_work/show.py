import json, sys, os

for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    print("=" * 70)
    for q, items in data.items():
        print("### QUERY:", q)
        for it in items:
            if "error" in it:
                print("  ERROR", it["error"])
                continue
            print(" -", it["title"])
            print("   lic:", it["license"], "|", it["licenseurl"])
            print("   size:", it["width"], "x", it["height"], "|", it["mime"])
            print("   page:", it["descpage"])
