"""Contact sheet of the final processed images, for a last visual check."""
import json
import os

from PIL import Image, ImageDraw

W = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(W)
OUT = os.path.join(W, "final_check.jpg")

with open(os.path.join(ROOT, "labels.json"), encoding="utf-8") as f:
    labels = json.load(f)

COLS, ROWS = 3, 3
CELL, LABEL = 300, 24
imgs = labels["images"]
per = COLS * ROWS
for si in range(0, len(imgs), per):
    batch = imgs[si:si + per]
    sheet = Image.new("RGB", (COLS * CELL, ROWS * (CELL + LABEL)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, e in enumerate(batch):
        r, c = divmod(i, COLS)
        im = Image.open(os.path.join(ROOT, e["file"])).convert("RGB")
        im.thumbnail((CELL, CELL))
        sheet.paste(im, (c * CELL + (CELL - im.width) // 2, r * (CELL + LABEL) + LABEL))
        d.text((c * CELL + 4, r * (CELL + LABEL) + 5), e["file"], fill=(0, 0, 0))
    name = "final_check_%02d.jpg" % (si // per + 1)
    sheet.save(os.path.join(W, name), quality=88)
    print(name, [e["file"] for e in batch])
