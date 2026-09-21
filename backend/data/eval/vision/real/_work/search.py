import requests, json, sys, time

S = requests.Session()
S.headers.update({"User-Agent": "HazardEvalBot/1.0 (vision eval dataset; local research)"})
API = "https://commons.wikimedia.org/w/api.php"


def search(q, limit=25, tries=5):
    p = {"action": "query", "format": "json", "generator": "search",
         "gsrsearch": "filetype:bitmap " + q, "gsrnamespace": "6", "gsrlimit": str(limit),
         "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": "1200"}
    last = None
    for i in range(tries):
        try:
            r = S.get(API, params=p, timeout=40)
            if r.status_code == 200 and r.text.lstrip()[:1] == "{":
                d = r.json()
                break
            last = "HTTP %s" % r.status_code
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        time.sleep(2.0 * (i + 1))
    else:
        raise RuntimeError(last)
    out = []
    for pid, pg in (d.get("query", {}).get("pages") or {}).items():
        ii = (pg.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata", {}) or {}

        def g(k):
            return em.get(k, {}).get("value")

        out.append({
            "title": pg.get("title"),
            "width": ii.get("width"), "height": ii.get("height"),
            "url": ii.get("url"), "thumb": ii.get("thumburl"),
            "license": g("LicenseShortName"), "licenseurl": g("LicenseUrl"),
            "artist": g("Artist"), "credit": g("Credit"),
            "descpage": ii.get("descriptionurl"),
            "mime": ii.get("mime"),
        })
    return out


if __name__ == "__main__":
    outpath = sys.argv[1]
    res = {}
    for q in sys.argv[2:]:
        try:
            res[q] = search(q)
        except Exception as e:
            res[q] = [{"error": str(e)}]
        time.sleep(0.4)
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("wrote", outpath, len(res))
