# -*- coding: utf-8 -*-
"""生成「极智平台迁移准备包」：知识库导入文件 + 五节点提示词 + 迁移映射表。

平台账号与用户指引到位后，可直接把这些文件导入平台知识库、把提示词粘进节点，
避免临时手忙脚乱。全部内容由仓库内真实数据/代码生成，不手写、不改写事实。

输出目录：docs/competition/platform_import/
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
OUT = REPO / "docs" / "competition" / "platform_import"


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def write(name: str, text: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(text, encoding="utf-8")
    return path


def kb_categories() -> str:
    data = load_json(BACKEND / "data" / "categories" / "category_catalog.json")
    lines = [
        "# 知识库导入 · 12345 事项分类目录（12 大类）",
        "",
        f"> 用途：平台知识库「事项分类」检索源。字段含定义、典型情形、易混淆辨析。",
        f"> 来源：{data.get('source', '')}｜版本：{data.get('schema_version', '')}",
        "> 实测：本目录配合留一交叉验证，事项分类准确率 72.2% → 100%（见 eval_classify.py）",
        "",
    ]
    for c in data["categories"]:
        lines += [
            f"## {c['name']}（{c['code']}）",
            f"- 定义：{c.get('definition', '')}",
            f"- 典型情形：{'、'.join(c.get('typical', []))}",
            f"- 易混淆辨析：{c.get('contrast', '')}",
            "",
        ]
    return "\n".join(lines)


def kb_departments() -> str:
    data = load_json(BACKEND / "data" / "departments" / "department_rules.json")
    lines = [
        "# 知识库导入 · 承办单位职责规则",
        "",
        "> 用途：平台知识库「职责判定」检索源；派单决策的主办/协办依据。",
        f"> 来源：{data.get('source_name', '芜湖市 12345 知识库（示例）')}｜说明：{data.get('notice', '')}",
        "",
    ]
    for r in data.get("rules", []):
        lines += [
            f"## {r.get('category_name', '')}（{r.get('category_code', '')}）",
            f"- 主办部门：{r.get('department', '')}",
            f"- 协办部门：{'、'.join(r.get('co_departments', []))}",
            f"- 识别关键词：{'、'.join(r.get('keywords', []))}",
            f"- 职责说明：{r.get('responsibilities', '')}",
            "",
        ]
    lines += [
        "## 属地主办原则（关键）",
        "- 依据《安徽省12345热线诉求闭环办理工作规范》：转办遵循「属地管理、分级负责」；",
        "  权责清晰事项可直接转承办单位，同时抄送属地 12345 热线主管部门督促协调。",
        "- 官方样例实测：89%（16/18）由属地政府/开发区承办，仅 11% 直派市直部门。",
        "- 属地区划：镜湖区、弋江区、鸠江区、湾沚区、繁昌区、南陵县、无为市、经济技术开发区、三山经济开发区、高新区（弋江区）。",
        "",
    ]
    return "\n".join(lines)


def kb_policies() -> str:
    ref = load_json(BACKEND / "data" / "policies" / "policy_references.json")
    lib = BACKEND / "data" / "policies" / "library"
    lines = [
        "# 知识库导入 · 政策依据索引",
        "",
        "> 用途：平台知识库「政策依据」检索源；答复引用须来自本清单（防虚构法条）。",
        "> 说明：法规全文已随仓库提供（backend/data/policies/library/），可整篇上传平台知识库。",
        "",
        "## 精选法规清单",
    ]
    for p in ref.get("policies", []):
        lines += [f"- **{p['name']}**", f"  - 适用范围：{p.get('scope', '')}", f"  - 使用说明：{p.get('usage', '')}"]
    files = sorted(lib.glob("*.txt")) if lib.exists() else []
    lines += ["", "## 全文文件清单（可整篇导入知识库）"]
    for f in files:
        lines.append(f"- {f.name}（{f.stat().st_size // 1024} KB）")
    lines += [
        "",
        "## 引用规则（写入提示词，务必保留）",
        "- 只引用本清单与知识库中实际存在的文件；政策库未覆盖的情形一律不引用；",
        "- 严禁虚构文件名；引用真实性由 QC 校验（不在库中的引用会被标记）。",
        "",
    ]
    return "\n".join(lines)


def kb_samples() -> str:
    rows = [
        json.loads(line)
        for line in (BACKEND / "data" / "processed" / "work_orders.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lines = [
        "# 知识库导入 · 官方样例工单（历史参考）",
        "",
        f"> 用途：平台知识库「相似历史工单」检索源（共 {len(rows)} 条）。",
        "> 注意：样例已脱敏（「某先生」式称呼、无完整联系方式），仅作参考，不得表述为现行权责。",
        "",
    ]
    for i, r in enumerate(rows, 1):
        lines += [
            f"## 样例 {i}｜{r.get('category', '')}",
            f"- 标题：{r.get('title', '')}",
            f"- 诉求：{r.get('request_content', '')[:300]}",
            f"- 历史办理单位：{'、'.join(r.get('handling_departments', []))}",
            f"- 官方答复（节选）：{r.get('reply_content', '')[:200]}",
            "",
        ]
    return "\n".join(lines)


PROMPT_ORDER = [
    ("understand", "① 诉求理解", "app/agents/understand.py"),
    ("work_order", "② 标准化工单", "app/agents/work_order.py"),
    ("classify", "③ 事项分类", "app/agents/classify.py"),
    ("route", "④ 承办单位推荐", "app/agents/route.py"),
    ("reply", "⑤ 答复草拟", "app/agents/reply.py"),
]


def extract_system(rel_path: str) -> str:
    text = (BACKEND / rel_path).read_text(encoding="utf-8")
    m = re.search(r'SYSTEM\s*=\s*"""(.*?)"""', text, re.S)
    return m.group(1).strip() if m else "（未找到 SYSTEM 提示词常量）"


def prompts_doc() -> str:
    lines = [
        "# 平台节点提示词（五节点）",
        "",
        "> 来源：仓库 `backend/app/agents/*.py` 的 SYSTEM 常量，原样导出、未改写。",
        "> 用法：平台工作流对应节点中，把「系统提示词」部分粘贴进大模型节点的 system 输入；",
        "> 「用户输入」部分按平台变量语法改写（本地用字符串拼接，平台用变量引用）。",
        "",
    ]
    for key, name, rel in PROMPT_ORDER:
        lines += [f"## {name}（{key}）", "", "```text", extract_system(rel), "```", ""]
    lines += [
        "## 附：知识支撑与规则引擎（非提示词，平台侧用知识库/代码块承载）",
        "- 规则引擎（确定性，建议平台用「代码块」节点实现）：",
        "  - `backend/app/services/dispatch.py` 三层派单决策（专业直派 → 属地主办 → 类别兜底）",
        "  - `backend/app/services/urgency.py` 急件分级 + 险种定级表",
        "  - `backend/app/services/deadline.py` 办理时限倒计时（工作日推进）",
        "  - `backend/app/services/reply_audit.py` 答复合规审查（9 类规则）",
        "  - `backend/app/data/dispatch/*.json`、`backend/data/compliance/reply_rules.json` 规则数据",
        "- 知识库：12 类目录 / 部门职责 / 政策法规 / 官方样例（见本目录其余文件）",
        "",
    ]
    return "\n".join(lines)


MAPPING = """# 极智平台迁移映射表（本地能力 → 平台节点）

> 目标：**核心工作流在平台内完整跑通**（赛制硬性要求），本地系统作为「外接测试系统」补充。
> 本表在拿到平台账号与用户指引后逐项落实；标「待确认」的需用平台文档核对。

## 一、主链路映射

| 本地节点/能力 | 平台实现方式 | 依赖/待确认 |
|---|---|---|
| 录音输入 | 工作流起始节点的文件/语音输入 | 平台**语音转文字节点当前不可用**（官方指南明确） |
| 双引擎转写（讯飞 + SenseVoice） | **平台内**：大模型节点选 `qwen3.5-omni-plus` 做转写（官方指定替代路径）<br>**增强**：HTTP 节点调用本地 `/api/asr` | 音频输入格式与时长上限、Token 消耗 |
| 领域词典纠错 + LLM 降噪 | 代码块节点（词典 JSON 内置）+ 大模型节点（降噪提示词） | 代码块能否读取内联 JSON（应可） |
| ① 诉求理解 | 大模型节点 + 结构化输出（提示词见 platform_import/平台提示词_五节点.md） | 结构化输出（JSON）支持方式 |
| ② 标准化工单 | 同上 | — |
| ③ 事项分类 | 大模型节点 + 知识库检索（12 类目录） | 知识库检索节点与重排器接法 |
| ④ 承办单位推荐 | 大模型节点 + 知识库（部门职责）+ **代码块规则锚定** | 代码块与知识库结果的变量传递 |
| ⑤ 答复草拟 | 大模型节点 + 知识库（政策法规）+ 引用校验（代码块） | 重排器 `gte-rerank-v2` / `text-embedding-v4` |
| 图片证据受理 | 大模型节点选 `qwen-vl-max`（视觉） | 图片输入格式与大小限制 |
| 急件分级 / 时限倒计时 | 代码块节点（险种定级表 + 工作日推进） | 代码块是否支持日期计算（Python 可用则应可） |
| 答复合规审查 | 代码块（9 类规则）+ 大模型节点（语义复核） | — |
| 人工确认（人在环） | 平台的对话流/工作流「人工确认」节点 + 输出结构化结果供审核 | **人工确认节点官方用法**（需用户指引） |
| 白盒轨迹 | 平台「运行日志逐节点回放」+ 本地轨迹抽屉 | 日志可见范围与导出 |
| 流转看板 / wiki / RBAC | **外接系统**：本地工作在公网/内网可达地址，平台 HTTP 节点跳转或回传 | 外接 HTTP 白名单与网络可达性 |
| 超期督办 | 平台触发器（定时）+ 记忆库（如有） | 触发器能力与频率 |

## 二、可用模型清单（官方指南已公布 10 个）

| 用途 | 平台模型 | 本地对应 |
|---|---|---|
| 语言/推理主判 | `deepseek-v4-pro`、`qwen-plus-latest` | DeepSeek deepseek-v4-flash |
| 交叉复核（异源） | `qwen-plus-latest` 或 `deepseek-R1` | 局域网 Qwen2.5-72B |
| 语音转写 | `qwen3.5-omni-plus` | 讯飞 v2 + SenseVoice |
| 图片理解 | `qwen-vl-max` | MiniMax-M3 |
| 检索向量 / 重排 | `text-embedding-v4`、`gte-rerank-v2` | bge-small-zh + BM25 |
| 决策模型（System One） | 平台未提供；Jev 走 TypeSafe/Vercel 外接 | Jev 已接入（待 Key） |

## 三、发布与自检（硬性三条）

1. 核心工作流在平台完整跑通、无断点；
2. 智能体命名：`团队名 + 智能体赛题名` → **aiwen12345热线工单智能生成与转派辅助智能体**（口径待群内确认）；
3. 发布到应用商店并**打开服务开关**，评审期内保持在线（截图留证）。

## 四、待平台信息确认清单

- [ ] 多模态输入：图片/音频的格式、大小、时长上限；是否支持 base64
- [ ] 人工确认/人在环节点的官方用法（审核 → 修改 → 继续/回退）
- [ ] 代码块节点能力（能否读外部 JSON、能否做日期运算、可用库）
- [ ] 知识库：文档格式、切分参数、检索与重排节点接法
- [ ] 触发器：是否支持定时任务、最短间隔
- [ ] 记忆库：能否按「诉求人/点位」跨会话检索（决定重复诉求识别方案）
- [ ] 外接 HTTP：白名单机制、内网可达性（决定本地工作台能否被评委访问）
- [ ] 双版本管理：A/B 两个提示词版本的评审可见性
"""


def main() -> int:
    files = {
        "知识库_12类目录.md": kb_categories(),
        "知识库_部门职责与属地原则.md": kb_departments(),
        "知识库_政策依据索引.md": kb_policies(),
        "知识库_官方样例工单.md": kb_samples(),
        "平台提示词_五节点.md": prompts_doc(),
        "平台迁移映射.md": MAPPING,
    }
    print("=== 生成平台迁移准备包 ===")
    for name, text in files.items():
        p = write(name, text)
        print(f"  {p.name:<34} {p.stat().st_size // 1024:>4} KB  {len(text.splitlines()):>4} 行")
    print(f"\n输出目录：{OUT}")
    print("用法：平台知识库按文件上传（12 类目录 / 部门职责 / 政策法规 / 样例工单）；")
    print("      平台节点提示词从「平台提示词_五节点.md」逐节复制；迁移对照见「平台迁移映射.md」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
