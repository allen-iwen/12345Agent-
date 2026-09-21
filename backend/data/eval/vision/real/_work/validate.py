"""Validate the vision eval dataset: PIL readability, size bounds, labels.json consistency."""
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = os.path.join(ROOT, "labels.json")
MAX_EDGE = 1024

ALLOWED_TYPES = {"井盖缺失", "道路破损", "垃圾堆积", "违章建筑", "占道经营",
                 "消防通道堵塞", "电线坠落", "其他"}
ALLOWED_SEVERITY = {"特急", "紧急", "一般"}

ok = True


def fail(msg):
    global ok
    ok = False
    print("  [FAIL]", msg)


def main():
    if not os.path.exists(LABELS):
        print("labels.json missing")
        return 1
    with open(LABELS, encoding="utf-8") as f:
        labels = json.load(f)

    print("schema_version:", labels.get("schema_version"))
    imgs = labels.get("images", [])
    print("declared images:", len(imgs))
    print()

    seen = set()
    per_type = {}
    total_bytes = 0
    for i, e in enumerate(imgs, 1):
        name = e.get("file", "")
        path = os.path.join(ROOT, name)
        print("[%02d] %s" % (i, name))
        if name in seen:
            fail("duplicate file entry")
        seen.add(name)
        if not os.path.exists(path):
            fail("file does not exist")
            continue
        total_bytes += os.path.getsize(path)

        try:
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                fmt, size = im.format, im.size
                im.load()
        except Exception as exc:
            fail("PIL cannot read: %r" % (exc,))
            continue

        print("     format=%s size=%dx%d bytes=%d" % (fmt, size[0], size[1], os.path.getsize(path)))
        if fmt != "JPEG":
            fail("format is %s, expected JPEG" % fmt)
        if max(size) > MAX_EDGE:
            fail("longest edge %d exceeds %d" % (max(size), MAX_EDGE))
        if min(size) < 200:
            fail("shortest edge %d too small to be useful" % min(size))

        ht = e.get("expected_hazard_type")
        if ht not in ALLOWED_TYPES:
            fail("expected_hazard_type %r not in allowed set" % ht)
        per_type[ht] = per_type.get(ht, 0) + 1
        if e.get("expected_severity") not in ALLOWED_SEVERITY:
            fail("expected_severity %r invalid" % e.get("expected_severity"))
        for key in ("source_page", "source_url", "author", "license", "license_url", "note"):
            if not e.get(key):
                fail("missing field %s" % key)
        if e.get("expected_hazard") is not True:
            fail("expected_hazard must be true")
        sp, su = e.get("source_page", ""), e.get("source_url", "")
        if not sp.startswith("http") or not su.startswith("http"):
            fail("source URLs must be http(s)")
        if "wikimedia.org" not in sp:
            fail("source_page is not a Wikimedia page: %s" % sp)

    # stray files in the output dir that labels.json does not cover
    for fn in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, fn)
        if os.path.isfile(p) and fn.lower().endswith((".jpg", ".jpeg", ".png")):
            if fn not in seen:
                print("  [warn] image on disk not in labels.json:", fn)

    print()
    print("=" * 62)
    print("REPORT")
    print("=" * 62)
    print("actual image count :", len(seen))
    print("total size         : %.2f MB (%d bytes)" % (total_bytes / 1048576.0, total_bytes))
    print("by hazard type:")
    for k in sorted(per_type, key=lambda x: -per_type[x]):
        print("   %-8s %d" % (k, per_type[k]))
    print("declared types     :", len(per_type), "/", len([t for t in ALLOWED_TYPES]))
    absent = [t for t in ALLOWED_TYPES if t != "其他" and t not in per_type]
    print("absent hazard types:", ", ".join(absent) if absent else "(none)")
    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
