"""Download small preview thumbnails of candidates and build a contact sheet index."""
import json
import os
import sys
import time

import requests

W = os.path.dirname(os.path.abspath(__file__))
S = requests.Session()
S.headers.update({"User-Agent": "HazardEvalBot/1.0 (vision eval dataset; local research)"})
PREV = os.path.join(W, "preview")
os.makedirs(PREV, exist_ok=True)


def thumb_url(rec, width=520):
    u = rec.get("thumb_url") or rec.get("source_url")
    # rebuild thumb url at requested width from the original filename
    if rec.get("source_url"):
        base = rec["source_url"]
        if "/commons/" in base:
            head, name = base.rsplit("/commons/", 1)
            return head + "/commons/thumb/" + name + "/%dpx-" % width + name.split("/")[-1]
    return u


if __name__ == "__main__":
    with open(os.path.join(W, "candidates.json"), encoding="utf-8") as f:
        cands = json.load(f)
    manifest = {}
    for i, (title, rec) in enumerate(sorted(cands.items()), 1):
        key = "c%02d" % i
        dest = os.path.join(PREV, key + ".jpg")
        if not os.path.exists(dest):
            ok = False
            for url in (thumb_url(rec), rec.get("thumb_url"), rec.get("source_url")):
                if not url:
                    continue
                try:
                    r = S.get(url, timeout=60)
                    if r.status_code == 200 and len(r.content) > 2000:
                        with open(dest, "wb") as fh:
                            fh.write(r.content)
                        ok = True
                        break
                except Exception as e:
                    print("err", key, e)
                time.sleep(0.6)
            if not ok:
                print("FAILED", key, title)
                continue
            time.sleep(0.6)
        manifest[key] = {"title": title, "license": rec["license"], "file": dest}
    with open(os.path.join(W, "preview_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("previews:", len(manifest))
