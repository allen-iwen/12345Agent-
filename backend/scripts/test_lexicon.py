# -*- coding: utf-8 -*-
"""领域纠错层验证：确定性替换 + 白盒记录，不走 LLM。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.transcript_clean import apply_domain_lexicon

CASES = [
    ("我家住在镜糊区弋矶山街道，门口印井盖没有了，很危险",
     ["镜糊区→镜湖区", "印井盖→窨井盖"]),
    ("戈江区那边非线充电的问题严重，物业不管",
     ["戈江区→弋江区", "非线充电→飞线充电"]),
    ("反映万止区夜化气更换难的问题",
     ["万止区→湾沚区", "夜化气→液化气"]),
    ("城关局的人来过，说这是围章建筑要拆",
     ["城关局→城管局", "围章建筑→违章建筑"]),
    ("镜湖区正常文本，不应有任何替换",
     []),
]

ok = True
for text, expects in CASES:
    out, changes = apply_domain_lexicon(text)
    hit = all(any(e in c for c in changes) for e in expects)
    untouched = not changes if not expects else True
    passed = hit and untouched
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {text[:18]}… → {out[:22]}… | {changes}")

sys.exit(0 if ok else 1)
