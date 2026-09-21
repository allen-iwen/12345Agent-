"""Download final images, normalize to JPEG <=1024px, and emit labels.json + README.md."""
import html
import io
import json
import os
import re
from datetime import date

import requests
from PIL import Image

W = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(W)  # the "real" output dir
S = requests.Session()
S.headers.update({"User-Agent": "HazardEvalBot/1.0 (vision eval dataset; local research)"})

DOWNLOAD_DATE = "2026-09-20"
MAX_EDGE = 1024
QUALITY = 85

# file-stem -> (hazard_type, severity, note)
PLAN = [
    ("Hard-manhole-open-01ASD", "manhole_missing_01", "井盖缺失", "特急",
     "路面井盖缺失，井口敞开，行人及车辆有坠落风险"),
    ("SEWER - Open Manhole - New Orleans September 2020", "manhole_missing_02", "井盖缺失", "特急",
     "路面井盖缺失，井口暴露于车行道，存在即时人身安全隐患"),

    ("Newport St James Street pothole in February 2010", "pothole_road_01", "道路破损", "一般",
     "沥青路面坑洼破损，车辆通行颠簸，暂无即时人身危险"),
    ("A Road filled with potholes", "pothole_road_02", "道路破损", "一般",
     "土石路面遍布坑洼与积水，车辆通行困难"),
    ("Damaged asphalt surface 5", "pothole_road_03", "道路破损", "一般",
     "沥青路面网裂、龟裂并伴有局部破损"),

    ("Fly tipping near High Beech, Essex", "garbage_dump_01", "垃圾堆积", "紧急",
     "林地被非法倾倒生活垃圾与杂物，影响面较大但无即时人身危险"),
    ("Garbage pile - panoramio", "garbage_dump_02", "垃圾堆积", "紧急",
     "小区垃圾收集点垃圾外溢堆积，环境卫生问题突出"),
    ("Brooklyn NY assorted photos 12 garbage bags near No Dumping sign", "garbage_dump_03", "垃圾堆积", "紧急",
     "禁止倾倒标识旁堆放大量垃圾袋，涉嫌非法倾倒"),

    ("Soweto township", "illegal_construction_01", "违章建筑", "紧急",
     "密集自建、私搭乱建棚户区，建筑间距与消防间距不足"),
    ("Slum in Benslimane Province, Morocco", "illegal_construction_02", "违章建筑", "紧急",
     "简易棚屋私搭乱建，缺规划许可与安全防护"),

    ("2015-05-01 street food carts on sidewalk in Taiwan", "vendor_sidewalk_01", "占道经营", "紧急",
     "流动餐车长期占据人行道，行人被迫绕行机动车道"),
    ("Vendor on sidewalk near a subway station near Dongdaemun Market", "vendor_sidewalk_02", "占道经营", "紧急",
     "摊贩在人行道及地铁口设摊，挤占公共通行空间"),

    ("Blocked exit in Songjiang, Shanghai 16 Feb 2026", "fire_lane_blocked_01", "消防通道堵塞", "特急",
     "超市疏散出口（安全出口）被货物托盘、手推车与梯子完全堵塞，火灾时无法疏散"),

    ("FEMA - 37240 - Down power lines in Texas", "fallen_wire_01", "电线坠落", "特急",
     "电线杆倾倒、线缆坠落于路面，存在触电与阻断通行风险"),
    ("Bezeq Cables Endanger Neighborhood Residents - כבלי בזק מסכנים תושבי שכונת עוני (4770635867)",
     "fallen_wire_02", "电线坠落", "特急",
     "电线杆严重倾斜、线缆被拉紧并低垂至人行道上方，高度不足且随时可能坠落，触电风险高"),
    ("Bucharest - crazy tangle of wires at the corner of Strada Matei Basarab and Strada Logofătul Udriște",
     "fallen_wire_03", "电线坠落", "特急",
     "架空线缆在电杆上严重缠绕并低垂下垂，高度不足，存在触电与坠落风险"),
]


def direct_url(rec):
    u = rec["source_url"].split("?")[0]
    return u


def url_candidates(rec, width=1280):
    """Ordered list of URLs to try: Special:FilePath, then the stored thumb host."""
    from urllib.parse import quote
    base = direct_url(rec)
    name = base.rsplit("/", 1)[-1]
    urls = [
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + quote(name, safe="") + "?width=%d" % width,
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/"
        + base.split("/commons/", 1)[1] + "/%dpx-" % width + name,
        base,
    ]
    thumb = rec.get("thumb_url")
    if thumb:
        urls.append(thumb.split("?")[0])
    return urls


def fetch_image(url, tries=6):
    import time
    last = None
    for i in range(tries):
        try:
            r = S.get(url, timeout=180)
            if r.status_code == 200 and len(r.content) > 3000:
                return r.content
            last = "HTTP %s (%d bytes)" % (r.status_code, len(r.content))
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        time.sleep(4.0 * (i + 1))
    raise RuntimeError(last)


def normalize(raw, dest):
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGB")
    im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    im.save(dest, "JPEG", quality=QUALITY, optimize=True, progressive=False)
    return im.size


def main():
    with open(os.path.join(W, "final_meta.json"), encoding="utf-8") as f:
        meta = json.load(f)

    images = []
    problems = []
    for stem, outname, htype, sev, note in PLAN:
        rec = meta.get("File:" + stem + ".jpg") or meta.get("File:" + stem + ".JPG")
        if rec is None:
            problems.append("metadata missing: " + stem)
            continue
        outname = outname + ".jpg"
        dest = os.path.join(ROOT, outname)
        raw = None
        errs = []
        for url in url_candidates(rec):
            try:
                raw = fetch_image(url, tries=2)
                break
            except Exception as e:
                errs.append("%s -> %s" % (url.split("/")[-1][:50], e))
        if raw is None:
            problems.append("%s: %s" % (outname, " | ".join(errs)))
            continue
        try:
            size = normalize(raw, dest)
        except Exception as e:
            problems.append("%s: normalize %s" % (outname, e))
            continue
        import time
        time.sleep(1.5)
        lic_url = rec["license_url"]
        if not lic_url:
            lic_url = rec["source_page"]
        images.append({
            "file": outname,
            "expected_hazard_type": htype,
            "expected_severity": sev,
            "expected_hazard": True,
            "note": note,
            "source_page": rec["source_page"],
            "source_url": direct_url(rec),
            "author": rec["author"] or "（见来源页面）",
            "license": rec["license"],
            "license_url": lic_url,
        })
        print("%-30s %-12s %-4s %s" % (outname, htype, sev, size))

    labels = {
        "schema_version": "1.0",
        "notice": "公开许可图片，逐张登记来源与许可证；仅用于视觉评测，不随作品再分发。",
        "images": images,
    }
    with open(os.path.join(ROOT, "labels.json"), "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("\nlabels.json:", len(images), "images")
    for p in problems:
        print("PROBLEM:", p)


if __name__ == "__main__":
    main()
