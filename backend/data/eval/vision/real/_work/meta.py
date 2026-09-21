"""Fetch full Commons metadata for selected File: titles and write candidates.json."""
import json
import re
import sys
import time

import requests

S = requests.Session()
S.headers.update({"User-Agent": "HazardEvalBot/1.0 (vision eval dataset; local research)"})
API = "https://commons.wikimedia.org/w/api.php"

TAG_RE = re.compile(r"<[^>]+>")


def clean(s):
    if not s:
        return ""
    s = TAG_RE.sub("", s)
    s = s.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    s = s.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", s).strip()


def fetch(titles, tries=5):
    out = {}
    for i in range(0, len(titles), 20):
        chunk = titles[i:i + 20]
        p = {"action": "query", "format": "json", "titles": "|".join(chunk),
             "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime|user",
             "iiurlwidth": "1600"}
        d = None
        for a in range(tries):
            try:
                r = S.get(API, params=p, timeout=45)
                if r.status_code == 200 and r.text.lstrip()[:1] == "{":
                    d = r.json()
                    break
            except Exception:
                pass
            time.sleep(1.5 * (a + 1))
        if d is None:
            print("FAILED chunk", chunk, file=sys.stderr)
            continue
        for pid, pg in (d.get("query", {}).get("pages") or {}).items():
            if "imageinfo" not in pg:
                print("MISSING", pg.get("title"), file=sys.stderr)
                continue
            ii = pg["imageinfo"][0]
            em = ii.get("extmetadata", {}) or {}

            def g(k):
                return em.get(k, {}).get("value")

            out[pg["title"]] = {
                "title": pg["title"],
                "source_page": ii.get("descriptionurl"),
                "source_url": ii.get("url"),
                "thumb_url": ii.get("thumburl"),
                "width": ii.get("width"),
                "height": ii.get("height"),
                "mime": ii.get("mime"),
                "author": clean(g("Artist")) or clean(g("Credit")) or ii.get("user") or "",
                "license": clean(g("LicenseShortName")),
                "license_url": clean(g("LicenseUrl")),
                "usage_terms": clean(g("UsageTerms")),
                "description": clean(g("ImageDescription"))[:400],
                "date": clean(g("DateTimeOriginal"))[:40],
            }
        time.sleep(0.5)
    return out


if __name__ == "__main__":
    with open(sys.argv[2], encoding="utf-8") as f:
        titles = json.load(f)
    res = fetch(titles)
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("wrote", sys.argv[1], len(res), "of", len(titles))
