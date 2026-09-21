"""Build labeled contact sheets from preview images."""
import json
import os
import sys

from PIL import Image, ImageDraw

W = os.path.dirname(os.path.abspath(__file__))
PREV = os.path.join(W, "preview")
OUT = os.path.join(W, "sheets")
os.makedirs(OUT, exist_ok=True)

COLS, ROWS = 3, 3
CELL = 300
LABEL = 22

with open(os.path.join(W, "preview_manifest.json"), encoding="utf-8") as f:
    man = json.load(f)

keys = sorted(man)
per = COLS * ROWS
for si in range(0, len(keys), per):
    batch = keys[si:si + per]
    sheet = Image.new("RGB", (COLS * CELL, ROWS * (CELL + LABEL)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, k in enumerate(batch):
        r, c = divmod(i, COLS)
        try:
            im = Image.open(man[k]["file"]).convert("RGB")
        except Exception as e:
            print("skip", k, e)
            continue
        im.thumbnail((CELL, CELL))
        x = c * CELL + (CELL - im.width) // 2
        y = r * (CELL + LABEL) + LABEL
        sheet.paste(im, (x, y))
        d.text((c * CELL + 4, r * (CELL + LABEL) + 4), k, fill=(0, 0, 0))
    name = "sheet_%02d.jpg" % (si // per + 1)
    sheet.save(os.path.join(OUT, name), quality=88)
    print(name, batch)
