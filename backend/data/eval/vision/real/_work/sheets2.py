"""Build contact sheets for the second preview batch."""
import json
import os

from PIL import Image, ImageDraw

W = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(W, "sheets2")
os.makedirs(OUT, exist_ok=True)

COLS, ROWS = 3, 3
CELL = 300
LABEL = 22

with open(os.path.join(W, "preview_manifest2.json"), encoding="utf-8") as f:
    man = json.load(f)

keys = sorted(man)
per = COLS * ROWS
for si in range(0, len(keys), per):
    batch = keys[si:si + per]
    sheet = Image.new("RGB", (COLS * CELL, ROWS * (CELL + LABEL)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, k in enumerate(batch):
        r, c = divmod(i, COLS)
        im = Image.open(man[k]["file"]).convert("RGB")
        im.thumbnail((CELL, CELL))
        x = c * CELL + (CELL - im.width) // 2
        y = r * (CELL + LABEL) + LABEL
        sheet.paste(im, (x, y))
        d.text((c * CELL + 4, r * (CELL + LABEL) + 4), k, fill=(0, 0, 0))
    name = "sheet2_%02d.jpg" % (si // per + 1)
    sheet.save(os.path.join(OUT, name), quality=88)
    print(name, batch)
