# -*- coding: utf-8 -*-
"""复赛提交包打包：方案 PPT + 演示视频 + 补充材料（源码快照可选），出包前做密钥扫描。

命名遵循赛制「团队名 + 智能体赛题名」。
视频：把录制好的 mp4 放到 `docs/competition/video/` 下（任意文件名），脚本自动收进包里；
      未放视频时会在报告中明确提示，其余材料照常打包（可录制后重跑本脚本）。

用法（仓库根或任意目录均可）：
    python backend/scripts/package_semifinal.py            # 含源码快照
    python backend/scripts/package_semifinal.py --no-src   # 仅材料（包更小）
"""
from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # 12345agent/
COMP = REPO / "docs" / "competition"
VIDEO_DIR = COMP / "video"
STAGE_ROOT = REPO.parent / "提交包"
PKG_NAME = "aiwen+12345热线工单智能生成与转派辅助智能体"
PKG_DIR = STAGE_ROOT / PKG_NAME
SRC_DIR = PKG_DIR / "源码快照"
ZIP_PATH = STAGE_ROOT / f"{PKG_NAME}.zip"

EXCLUDE_DIRS = {".git", "venv", "node_modules", "__pycache__", ".pytest_cache",
                "storage", "raw", ".tools", "ui_shots", "video"}
EXCLUDE_FILES = {".env", ".env.local", "backend_run.log", "backend_err.log", "DS_Store"}
EXCLUDE_EXT = {".pyc", ".sqlite3", ".log", ".mp3", ".wav", ".xlsx"}

SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9]{16,}"), "LLM/视觉 API Key"),
    (re.compile(r"sk-cp-[a-zA-Z0-9\-]{20,}"), "MiniMax Key"),
    (re.compile(r"gho_[a-zA-Z0-9]{20,}"), "GitHub OAuth token"),
    (re.compile(r"ghp_[a-zA-Z0-9]{20,}"), "GitHub PAT"),
    (re.compile(r"(api_?key|apikey|secret|password)\s*[=:]\s*['\"][A-Za-z0-9\-_]{16,}", re.I), "硬编码密钥"),
]

MATERIALS = [
    ("02_复赛方案.pptx", "复赛方案 PPT（16 页）"),
    ("11_实操案例_CodingAgent使用过程.pdf", "实操案例：Coding Agent 使用过程记录（含界面截图）"),
    ("03_演示视频脚本.md", "演示视频脚本（4 分 30 秒分镜）"),
    ("01_创意说明书.md", "创意说明书（初赛材料，作为背景参考）"),
    ("07_核心竞争力设计.md", "核心竞争力设计与实测证据"),
    ("08_验证报告.md", "端到端验证报告（20 项自动核查）"),
    ("09_决策模型评测_laya.md", "决策模型评测（开源 laya 与闭源 JEV 双通道实测）"),
    ("10_实操案例_CodingAgent过程记录.md", "完整过程记录（由会话记录导出的全文，可检索）"),
    ("06_复赛开发计划.md", "复赛开发计划与平台迁移路径"),
    ("architecture.png", "技术架构图（PNG）"),
    ("architecture.svg", "技术架构图（矢量）"),
    ("flow.png", "业务流程图（PNG）"),
    ("flow.svg", "业务流程图（矢量）"),
]


def iter_source_files():
    for p in REPO.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(REPO)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if p.name in EXCLUDE_FILES or p.suffix.lower() in EXCLUDE_EXT:
            continue
        yield p, rel


def scan_secrets(root: Path) -> list[str]:
    hits: list[str] = []
    exts = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".txt", ".yml", ".yaml", ".example", ".html", ".css"}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if "http" in line or "replace_me" in line or "EMPTY" in line:
                continue  # 公开 URL / 占位符不算密钥
            for pat, name in SECRET_PATTERNS:
                for m in pat.finditer(line):
                    if m.group(0).isdigit():
                        continue
                    hits.append(f"{name}: {p.relative_to(root)}:{line_no} → {m.group(0)[:12]}…")
    return hits


def main() -> int:
    with_src = "--no-src" not in sys.argv
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)

    included: list[str] = []
    missing: list[str] = []
    for name, desc in MATERIALS:
        src = COMP / name
        if src.exists():
            shutil.copy2(src, PKG_DIR / name)
            included.append(f"{name}　—　{desc}")
        else:
            missing.append(name)

    # 演示视频（可选）
    video_files = sorted(VIDEO_DIR.glob("*.mp4")) if VIDEO_DIR.exists() else []
    if video_files:
        for v in video_files:
            shutil.copy2(v, PKG_DIR / v.name)
            included.append(f"{v.name}　—　演示视频（{v.stat().st_size // 1048576} MB）")
    else:
        missing.append("演示视频（把 mp4 放到 docs/competition/video/ 后重跑本脚本）")

    # 源码快照（可选）
    if with_src:
        n = 0
        for p, rel in iter_source_files():
            dest = SRC_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(p.read_bytes())
            n += 1
        included.append(f"源码快照/　—　{n} 个文件（不含密钥、数据库、原始数据集）")

    # 材料说明
    (PKG_DIR / "材料说明.txt").write_text(
        f"{PKG_NAME}　复赛提交材料\n"
        "=" * 56 + "\n"
        "【必交】极智平台可运行智能体 Demo：按平台要求发布到应用商店并保持服务开启\n"
        "【必交】复赛作品方案：02_复赛方案.pptx\n"
        f"【必交】3–5 分钟演示视频：{'已包含 ' + video_files[0].name if video_files else '待录制（见 03_演示视频脚本.md）'}\n"
        "【可选】补充材料：创意说明书、核心竞争力设计、开发计划、架构图与流程图、源码快照\n\n"
        "来源与合规声明\n"
        "- 官方样例工单与录音来自赛题数据集，仅本地使用、未随包再分发；\n"
        "- 政策法规来自政府公开渠道，名称与来源已在代码中逐条登记；\n"
        "- 视觉评测图集来自 Wikimedia Commons（CC/公有领域），逐张登记作者与许可证；\n"
        "- 本包含源码快照但不含任何密钥、数据库、录音与原始数据集；打包前已做密钥扫描。\n",
        encoding="utf-8",
    )

    hits = scan_secrets(PKG_DIR)
    if hits:
        print("!!! 发现疑似敏感内容，中止打包：")
        for h in hits:
            print("   ", h)
        return 1
    print("密钥扫描：干净")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(PKG_DIR.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(STAGE_ROOT))

    size_mb = ZIP_PATH.stat().st_size / 1048576
    print(f"\n打包完成：{ZIP_PATH}　{size_mb:.1f} MB（上限 200MB）")
    print("\n已包含：")
    for x in included:
        print("  ✓", x)
    if missing:
        print("\n尚缺：")
        for x in missing:
            print("  ✗", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
