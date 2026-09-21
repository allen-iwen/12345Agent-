# -*- coding: utf-8 -*-
"""生成复赛参赛方案 PPTX（政务编辑风：白底墨字 + 单一主色 + 细线分隔，无装饰图标）。

数据来源：本项目本轮实测结果（脚本可复现，见末页命令清单）。
用法：python scripts/make_deck.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[2]  # 仓库根 12345agent/
OUT = ROOT / "docs" / "competition" / "02_复赛方案.pptx"
SHOTS = ROOT.parent / "ui_shots"

INK = RGBColor(0x1C, 0x24, 0x30)
MUT = RGBColor(0x66, 0x70, 0x7C)
LIGHT = RGBColor(0x98, 0xA1, 0xAC)
TEAL = RGBColor(0x0F, 0x76, 0x6E)
TEAL_DK = RGBColor(0x0B, 0x5D, 0x56)
BORDER = RGBColor(0xCF, 0xCF, 0xC9)
HAIR = RGBColor(0xE4, 0xE4, 0xDF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
WARN = RGBColor(0xB4, 0x53, 0x09)
DANGER = RGBColor(0xC8, 0x1E, 0x3C)
GREEN = RGBColor(0x15, 0x80, 0x3D)
BG = RGBColor(0xFA, 0xFA, 0xF8)

FONT = "微软雅黑"
SW, SH = Inches(13.333), Inches(7.5)


def new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = SW, SH
    return prs


def slide(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def textbox(s, x, y, w, h, lines, *, size=13, color=INK, bold=False, align=PP_ALIGN.LEFT,
            line_spacing=1.25, font=FONT):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(lines):
        text, opts = (item, {}) if isinstance(item, str) else item
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = opts.get("align", align)
        p.line_spacing = opts.get("line_spacing", line_spacing)
        if opts.get("space_before"):
            p.space_before = Pt(opts["space_before"])
        run = p.add_run()
        run.text = text
        run.font.size = Pt(opts.get("size", size))
        run.font.bold = opts.get("bold", bold)
        run.font.color.rgb = opts.get("color", color)
        run.font.name = font
    return tb


def rect(s, x, y, w, h, fill=None, line=BORDER, line_w=0.75, radius=False):
    from pptx.enum.shapes import MSO_SHAPE

    shape = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h),
    )
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_w)
    shape.shadow.inherit = False
    if radius:
        shape.adjustments[0] = 0.06
    return shape


def header(s, no: str, title: str, sub: str = ""):
    """统一页眉：编号 + 标题 + 细线（编辑风）。"""
    textbox(s, 0.7, 0.42, 10.5, 0.5, [(f"{no}　{title}", {"size": 24, "bold": True})])
    if sub:
        textbox(s, 0.7, 1.02, 11.9, 0.4, [(sub, {"size": 11.5, "color": MUT})])
    rect(s, 0.7, 1.44 if sub else 1.06, 11.93, 0.012, fill=BORDER, line=None)


def footer(s, text: str = "aiwen ｜ 12345 热线工单智能生成与转派辅助智能体"):
    textbox(s, 0.7, 7.02, 9.0, 0.3, [(text, {"size": 9, "color": LIGHT})])
    textbox(s, 10.6, 7.02, 2.0, 0.3, [("复赛方案 · 2026-09", {"size": 9, "color": LIGHT, "align": PP_ALIGN.RIGHT})])


def table(s, x, y, w, h, rows: list[list[str]], *, widths=None, head=True, size=10.5,
          head_fill=TEAL, head_color=WHITE):
    shape = s.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(h))
    tbl = shape.table
    if widths:
        total = sum(widths)
        for i, frac in enumerate(widths):
            tbl.columns[i].width = Emu(int(Inches(w) * frac / total))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = str(val)
            cell.margin_left = cell.margin_right = Inches(0.07)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = 1  # middle
            p = cell.text_frame.paragraphs[0]
            p.line_spacing = 1.05
            for run in p.runs:
                run.font.size = Pt(size)
                run.font.name = FONT
                run.font.color.rgb = head_color if (head and r == 0) else INK
                run.font.bold = head and r == 0
            if head and r == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = head_fill
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = WHITE if r % 2 else BG
    return tbl


def bullets(s, x, y, w, items: list[str], *, size=12.5, gap=0.42, color=INK):
    for i, it in enumerate(items):
        textbox(s, x, y + i * gap, w, gap, [("·  " + it, {"size": size, "color": color})])


def metric_row(s, y, items: list[tuple[str, str, RGBColor]]):
    """指标卡：数值 + 说明。"""
    n = len(items)
    gap = 0.29
    w = (11.93 - gap * (n - 1)) / n
    for i, (value, label, color) in enumerate(items):
        x = 0.7 + i * (w + gap)
        rect(s, x, y, w, 1.02, fill=BG, line=HAIR)
        textbox(s, x + 0.12, y + 0.12, w - 0.24, 0.42, [(value, {"size": 20, "bold": True, "color": color})])
        textbox(s, x + 0.12, y + 0.58, w - 0.24, 0.38, [(label, {"size": 9.5, "color": MUT})])


# ---------------------------------------------------------------- slides

def s01_cover(prs):
    s = slide(prs)
    rect(s, 0, 0, 13.333, 0.16, fill=TEAL, line=None)
    textbox(s, 1.1, 1.55, 11, 0.5, [("2026 长三角（芜湖）算力算法创新应用大赛 · 智能体赛道", {"size": 13, "color": MUT})])
    textbox(s, 1.1, 2.15, 11.2, 1.5, [
        ("12345 热线工单智能生成与转派辅助智能体", {"size": 36, "bold": True}),
        ("—— 从「工单文书生成」到「派单决策与诉求治理」", {"size": 17, "color": TEAL_DK, "space_before": 14}),
    ])
    rect(s, 1.1, 4.15, 4.2, 0.012, fill=BORDER, line=None)
    textbox(s, 1.1, 4.45, 11, 1.6, [
        ("团队：aiwen（创客个人）　负责人：王同鹤", {"size": 13}),
        ("一句话：录音 / 文本 / 现场照片进，可派发工单与合规答复出——每一步可查、可改、可追溯，放行权永远在人。", {"size": 12.5, "color": MUT, "space_before": 10}),
        ("实测：事项分类留一验证 100%｜主办单位推荐 94.4%（通用做法仅 5.6%）｜单案 35–70 秒（人工工序基准约 20 分钟，估算）", {"size": 12, "color": TEAL_DK, "space_before": 10}),
    ])
    footer(s)


def s02_agenda(prs):
    s = slide(prs)
    header(s, "01", "方案概览", "六部分：场景理解 → 竞争判断 → 技术方案 → 数据与模型 → 测试结果 → 演示与计划")
    items = [
        ("场景理解", "四类真实痛点：整理效率低、分类靠经验、部门匹配耗时、回复质量不一致"),
        ("竞争判断", "通用做法（按类别推部门）实测命中率仅 5.6%——方向上就错了"),
        ("技术方案", "五节点白盒链路 +「五把关」：受理 / 决策 / 答复 / 时限 / 合规"),
        ("数据与模型", "官方样例 + 公开政策 + 公开许可图集；生成模型负责写、决策模型负责判"),
        ("测试结果", "六项可复现指标，全部来自真实调用，未做任何人工修饰"),
        ("演示与计划", "8 项必展示功能全覆盖；复赛平台迁移路径与在芜落地计划"),
    ]
    for i, (t, d) in enumerate(items):
        y = 1.85 + i * 0.82
        textbox(s, 0.7, y, 1.6, 0.4, [(t, {"size": 14, "bold": True, "color": TEAL_DK})])
        textbox(s, 2.35, y, 10.3, 0.5, [(d, {"size": 12.5, "color": INK})])
        if i < len(items) - 1:
            rect(s, 0.7, y + 0.66, 11.93, 0.01, fill=HAIR, line=None)
    footer(s)


def s03_scene(prs):
    s = slide(prs)
    header(s, "02", "场景理解与核心问题", "12345 的痛点不在「能不能答」，而在「每一单都要人来抠细节」")
    bullets(s, 0.7, 1.85, 6.0, [
        "工单整理效率低：接线员边听边记，要素靠手工整理，格式不统一",
        "分类依赖经验：新人面对 12 大类与职责交叉，容易派错部门",
        "部门匹配耗时：派错就要退回重派，是热线最耗时的环节",
        "回复质量不一致：口径因人而异，个别答复还会承诺过度",
    ], gap=0.62)
    rect(s, 7.0, 1.8, 5.63, 3.3, fill=BG, line=HAIR)
    textbox(s, 7.25, 1.98, 5.13, 3.0, [
        ("我们的定位", {"size": 14, "bold": True, "color": TEAL_DK}),
        ("坐席的辅助副驾——不是替代人，而是替人把关：", {"size": 12, "space_before": 8}),
        ("· 把录音快速变成忠实原文的结构化工单", {"size": 11.5, "color": MUT}),
        ("· 给出可解释的分类与派单建议（含依据与退回风险）", {"size": 11.5, "color": MUT}),
        ("· 答复先过合规闸门，超期自动督办", {"size": 11.5, "color": MUT}),
        ("· 机器只出建议，放行权永远在人", {"size": 11.5, "color": TEAL_DK, "space_before": 6}),
    ])
    textbox(s, 0.7, 5.35, 11.93, 1.2, [
        ("另外两个真实业务诉求我们也做了：同类诉求短期聚集应触发「未诉先办」预警；效率提升应可量化（基层减负账本）。", {"size": 12, "color": MUT}),
    ])
    footer(s)


def s04_competition(prs):
    s = slide(prs)
    header(s, "03", "竞争判断：通用做法错在哪（本方案最硬的一条证据）",
           "用官方 18 条样例工单的历史实际承办单位做验证——不是我们自说自话")
    rows = [
        ["派单策略", "主办单位命中率", "依据"],
        ["通用做法：按事项类别推市直部门（多数队伍会这么做）", "5.6%（1/18）", "直觉推断"],
        ["本方案：三层决策（专业直派 → 属地主办 → 类别兜底）", "94.4%（17/18）", "省级规范 + 历史实证"],
    ]
    table(s, 0.7, 1.85, 11.93, 1.5, rows, widths=[6.2, 2.6, 3.1], size=11.5)
    rect(s, 0.7, 3.6, 11.93, 1.05, fill=BG, line=HAIR)
    textbox(s, 0.95, 3.75, 11.4, 0.8, [
        ("官方样例实测：89%（16/18）由属地政府 / 开发区承办，仅 11% 直派市直部门——与《安徽省12345热线诉求闭环办理工作规范》"
         "「属地管理、分级负责」原则完全一致。", {"size": 12, "color": INK}),
    ])
    bullets(s, 0.7, 4.95, 11.9, [
        "结论一：通用做法从方向上就错——把「属地主办」当成了「部门直派」",
        "结论二：政务派单的正确抽象是「属地 + 部门」双维度，不是单选题",
        "结论三：这条规则可复现、可审计（backend/scripts/eval_dispatch.py）",
    ], gap=0.5, size=12)
    footer(s)


def s05_architecture(prs):
    s = slide(prs)
    header(s, "04", "整体方案：五节点白盒链路 + 五把关", "受理把关 → 决策把关 → 答复把关 → 时限把关 → 合规贯穿")
    arch = ROOT / "docs" / "competition" / "architecture.png"
    if arch.exists():
        s.shapes.add_picture(str(arch), Inches(2.42), Inches(1.62), width=Inches(8.5))
    textbox(s, 0.7, 6.35, 11.93, 0.6, [
        ("底座：依据链可追溯 + 白盒轨迹（每节点输入输出/耗时留痕）+ 操作审计（谁审的、谁改的可追）", {"size": 11.5, "color": MUT}),
    ])
    footer(s)


def s06_dispatch(prs):
    s = slide(prs)
    header(s, "05", "决策把关：属地 + 部门双维派单", "三层决策 + 依据链 + 退回风险，规则锚定、模型复核，分歧交人工")
    rows = [
        ["决策层", "触发情形", "输出"],
        ["① 专业直派", "行业性极强的诉求（公交运营、消费维权等）", "专业承办单位（如 市公安局 + 芜湖公交公司）"],
        ["② 属地主办", "有明确属地区划（89% 的情形）", "属地区县政府 / 开发区管委会 主办"],
        ["③ 类别兜底", "未识别到属地", "按事项类别推市直部门，并提示人工确认属地"],
    ]
    table(s, 0.7, 1.8, 11.93, 1.9, rows, widths=[1.9, 4.9, 5.1], size=11)
    textbox(s, 0.7, 3.9, 11.93, 0.4, [("每次派单都给出完整决策包（示例：烧烤店占道经营案）", {"size": 13, "bold": True, "color": TEAL_DK})])
    bullets(s, 0.7, 4.35, 11.9, [
        "主办：鸠江区政府（依据：属地管理原则 + 历史同类工单 89% 由属地承办）",
        "协办/指导：市城市管理局（占道经营职责）、市生态环境局（油烟）",
        "退回风险：职责交叉（主办 + 协办组合），历史上易被退回，建议派前协调并抄送属地热线主管部门",
        "分歧处理：规则判定与模型复核不一致时，标记需人工裁断并同时展示双方结论",
    ], gap=0.5, size=11.5)
    footer(s)


def s07_urgency(prs):
    s = slide(prs)
    header(s, "06", "时限把关：险种定级 + 倒计时督办", "依据规范「紧急事项 24 小时内反馈进展」，把建议变成可考核的时钟")
    rows = [
        ["等级", "触发", "建议时限与动作"],
        ["特急", "井盖缺失、电线坠落、消防通道堵塞、燃气泄漏、危房", "30 分钟内电话通知承办单位 + 24 小时内反馈进展"],
        ["紧急", "大面积停水停电、环境污染、成片垃圾、占道经营阻碍通行", "当日派件 + 24 小时内反馈进展"],
        ["一般", "咨询、建议、非安全类投诉", "规定时限内办结；复杂事项可「承诺办理」（≤9 个月）"],
    ]
    table(s, 0.7, 1.8, 11.93, 2.0, rows, widths=[1.2, 5.9, 4.8], size=11)
    bullets(s, 0.7, 4.1, 11.9, [
        "到期时刻按工作日推进（跳过周末与法定节假日、支持调休）；节假日数据缺失时显式标注，不凭空填写日期",
        "状态：正常 / 临期（剩余 ≤20% 或 ≤4h）/ 超期；超期自动附督办建议（规范：多次反映且办理不到位可联合督查机构专项督办）",
        "诚实标注：一般件工作日数为建议值（待与芜湖市办理细则核对），不虚构条款",
    ], gap=0.5, size=11.5)
    footer(s)


def s08_vision(prs):
    s = slide(prs)
    header(s, "07", "受理把关：多模态图片证据", "市民上传现场照片 → 视觉模型判读 → 影响事项分类与急件分级")
    metric_row(s, 1.75, [
        ("93.8%", "隐患类型识别准确率\n（16 张公开许可图集）", TEAL_DK),
        ("100%", "隐患有无一致率\n（不漏报、不脑补）", GREEN),
        ("2.7–5.7s", "单张判读延迟\n（MiniMax-M3）", INK),
        ("100%", "图片证据入链成功率\n（含 JSON 修复回退）", TEAL_DK),
    ])
    textbox(s, 0.7, 3.05, 11.93, 0.4, [("比数字更重要的一个工程结论", {"size": 13, "bold": True, "color": TEAL_DK})])
    bullets(s, 0.7, 3.5, 11.9, [
        "实测发现：模型自报的「严重程度」跨次不稳定（同批图片两次评测 73.3% vs 50.0%），而险种识别稳定",
        "因此改为**按险种定级**：井盖缺失/电线坠落/消防通道堵塞 → 特急；垃圾堆积/占道经营/违建 → 紧急；道路破损 → 一般",
        "验证：模型 severity 故意报「一般」，系统仍按险种正确升级为特急（8/8 通过）——不盲信模型分数",
        "合规约束：只描述可见事实、不推测身份、禁输出人脸/车牌/门牌；模型不可用时降级为人工判读，链路零回归",
    ], gap=0.5, size=11.5)
    footer(s)


def s09_reply_audit(prs):
    s = slide(prs)
    header(s, "08", "答复把关：合规审查（退回重办风险）", "依据规范「答复须正面回应、列明政策依据，经审核不规范将退回重办」")
    rows = [
        ["审查维度", "典型问题", "处理"],
        ["过度承诺 / 时限承诺", "「保证解决」「承诺三天内办结」", "命中即提示改为按程序表述"],
        ["绝对化用语", "「彻底杜绝」「100% 解决」", "建议改为持续加强管理"],
        ["隐私泄露", "答复中出现手机号、身份证号、精确门牌", "高风险，须删除（谁管理、谁负责）"],
        ["推诿表述", "「不归我们管」「你去找」", "改为已转交 ×× 部门办理"],
        ["未正面回应 / 隐患缺安全提示 / 规范要素 / 引用不可溯", "只讲流程、缺必备提示、引用虚构法规", "逐条给出修改建议"],
    ]
    table(s, 0.7, 1.8, 11.93, 2.9, rows, widths=[3.4, 4.6, 3.9], size=10.5)
    metric_row(s, 5.15, [
        ("100%", "违规答复召回（10/10）", GREEN),
        ("0%", "合规答复误报（0/10）", GREEN),
        ("9 类", "确定性规则（可解释、可审计）", INK),
        ("可叠加", "LLM 语义复核（只补充发现，不改判定）", TEAL_DK),
    ])
    footer(s)


def s10_trust(prs):
    s = slide(prs)
    header(s, "09", "可信性设计：决策模型 + 交叉复核 + 白盒轨迹", "政务场景不落地的根因是「不敢信」——我们把不确定性显式交给人")
    cards = [
        ("System One 决策模型（Jev）", [
            "判断交给决策模型、写作交给生成模型",
            "Noul / Choice / Score 三类原语返回校准概率",
            "已接通四个判断点：分类 / 急件 / 派单 / 合规",
            "契约照官方 OpenAPI；未配置或失败自动回退（零回归）",
        ]),
        ("双模型交叉复核", [
            "另一模型独立判断同一问题，避免单模型自证",
            "一致 → 记录复核一致；分歧 → 标记需人工判断",
            "实测：主判与局域网复核模型一致 2/2",
            "代价如实记录：复核使单案 30s → 110–137s，默认关闭",
        ]),
        ("白盒轨迹与审计", [
            "每节点输入/输出/耗时入库，可回放",
            "流转日志记录谁、何时、从哪到哪、依据",
            "六类角色 RBAC：坐席/派单员/审核员/部门/管理员/监督员",
            "操作审计只插入不可改，满足「谁审的、谁改的」可追责",
        ]),
    ]
    for i, (title, items) in enumerate(cards):
        x = 0.7 + i * 4.05
        rect(s, x, 1.8, 3.85, 4.4, fill=WHITE, line=BORDER)
        textbox(s, x + 0.22, 1.98, 3.4, 0.5, [(title, {"size": 13, "bold": True, "color": TEAL_DK})])
        rect(s, x + 0.22, 2.5, 3.4, 0.01, fill=HAIR, line=None)
        textbox(s, x + 0.22, 2.62, 3.45, 3.4, [
            ("· " + it, {"size": 10.5, "color": INK, "space_before": 6}) for it in items
        ])
    footer(s)


def s11_flow_wiki(prs):
    s = slide(prs)
    header(s, "10", "工单流转与知识运营", "从「办单」到「治事」：状态机看板 + 口径层 wiki + 权限审计")
    rows = [
        ["模块", "内容", "状态"],
        ["工单流转状态机", "已受理→已分类→已派单→签收→办理→回执→审核→归档（含退回、承诺办理旁路）", "15 条迁移 + 双层守卫，19/19"],
        ["流转看板", "按状态分列、就地流转、临期/超期角标、超期督办提示", "界面 19/19"],
        ["知识词条（wiki）", "口径层：办理经验/答话口径/案例复盘，草稿→发布、逐版可回看", "15/15"],
        ["智能体回写", "案件定稿后一键沉淀为词条草稿（派单结论 + 答复口径 + 政策依据）", "已实现"],
        ["RBAC 与审计", "6 角色权限矩阵 + 关键操作守卫 + 操作审计（启用态 12/12）", "渐进启用，默认关闭"],
    ]
    table(s, 0.7, 1.8, 11.93, 3.4, rows, widths=[2.3, 7.3, 2.3], size=10.5)
    textbox(s, 0.7, 5.5, 11.93, 0.9, [
        ("依据层（政策库 / 部门职责 / 12 类目录，决定判断）与口径层（wiki，统一表达）分工明确，互不污染生成。",
         {"size": 11.5, "color": MUT}),
    ])
    footer(s)


def s12_data_model(prs):
    s = slide(prs)
    header(s, "11", "数据、模型与第三方工具使用说明", "合规硬要求：来源可溯、许可清晰、脱敏到位")
    rows = [
        ["类别", "具体内容", "来源与许可"],
        ["官方数据", "18 条样例工单（含历史实际承办单位）+ 配套录音", "赛题官方数据集；仅本地使用、未再分发"],
        ["公开政策", "8 部法规全文 + 芜湖公开政策文件", "政府公开渠道，名称与来源逐条登记"],
        ["评测图集", "16 张城市隐患照片", "Wikimedia Commons；逐张登记作者与许可证（CC/公有领域）"],
        ["生成模型", "DeepSeek（主判/写作）、局域网 Qwen2.5-72B（复核）", "API 调用；复核模型与主判异源"],
        ["决策模型", "Jev / TypeSafe System One（已接入，待 Key 启用）", "官方 OpenAPI 契约；失败自动回退"],
        ["视觉模型", "MiniMax-M3（图片判读）", "OpenAI 兼容接口；仅传图片，不传个人信息"],
        ["向量与检索", "bge-small-zh-v1.5 + Chroma；BM25", "BAAI 公开模型；本地推理，无外传"],
    ]
    table(s, 0.7, 1.8, 11.93, 4.1, rows, widths=[1.7, 5.5, 4.7], size=10)
    textbox(s, 0.7, 6.05, 11.93, 0.7, [
        ("脱敏与隐私：官方样例已脱敏（「某先生」式称呼、无完整联系方式）；评测图集剔除含人脸/车牌/门牌的照片；密钥仅存本地 .env，不入仓库与提交包。",
         {"size": 10.5, "color": MUT}),
    ])
    footer(s)


def s13_results(prs):
    s = slide(prs)
    header(s, "12", "测试样本与测试结果", "六项指标全部来自真实调用与可复现脚本，未做任何人工修饰")
    rows = [
        ["评测项", "方法", "结果"],
        ["事项分类准确率", "官方 18 条留一交叉验证（防答案泄漏）", "100%（基线 72.2%）"],
        ["主办单位推荐命中率", "同集对照官方历史实际承办单位", "94.4%（通用做法 5.6%）"],
        ["图片隐患类型识别", "16 张公开许可图集，不透露期望答案", "93.8%（隐患有无一致率 100%）"],
        ["答复合规审查", "10 条违规 + 10 条合规构造集", "召回 100%｜误报 0%"],
        ["办理时限计算", "12 条用例（工作日/自然日/临期/超期/办结）", "12/12 通过"],
        ["流转与权限", "主线全链路迁移 + 角色矩阵", "流转 19/19｜RBAC 12/12"],
    ]
    table(s, 0.7, 1.8, 11.93, 3.4, rows, widths=[3.0, 5.7, 3.2], size=10.5)
    textbox(s, 0.7, 5.5, 11.93, 1.2, [
        ("效率对比：单案五节点全链路 35–70 秒（实测 34.5s / 68.5s，随模型延迟波动）vs 人工工序基准约 20 分钟（8′+4′+8′ 估算）；"
         "开启双模型交叉复核时 110–137 秒（可配置关闭）。", {"size": 11.5, "color": INK}),
        ("全部命令见末页；每条结论都能在评委机器上重跑复现。", {"size": 11, "color": MUT, "space_before": 6}),
    ])
    footer(s)


def s14_demo(prs):
    s = slide(prs)
    header(s, "13", "系统演示：8 项必展示功能全覆盖", "以下功能均已在本地跑通并通过自动化验证")
    feats = [
        "① 录音输入与文本输入（双引擎转写 + 降噪整理）",
        "② 群众诉求理解及关键信息提取（时间/地点/人员/事件/诉求）",
        "③ 标准化工单生成（标题/摘要/要素/诉求）",
        "④ 事项类别推荐（12 类 + 候选得分 + 置信度）",
        "⑤ 承办单位推荐（主办/协办 + 依据链 + 退回风险）",
        "⑥ 预回复与回访话术（含政策依据，引用真实性校验）",
        "⑦ 人工查看/审核/修改（分节确认、修改后重跑、最终放行）",
        "⑧ 信息不足/职责交叉提示（含图片证据与置信度门控）",
    ]
    for i, f in enumerate(feats):
        col, row = divmod(i, 4)
        x = 0.7 + col * 6.1
        y = 1.85 + row * 0.72
        rect(s, x, y, 5.83, 0.6, fill=BG, line=HAIR)
        textbox(s, x + 0.18, y + 0.13, 5.5, 0.42, [(f, {"size": 11})])
    shots = [SHOTS / "18_flow_board.png", SHOTS / "17_photo_evidence.png", SHOTS / "20_wiki_entries.png"]
    x = 0.7
    for shot in shots:
        if shot.exists():
            s.shapes.add_picture(str(shot), Inches(x), Inches(4.95), height=Inches(1.55))
            x += 4.1
    footer(s)


def s15_plan(prs):
    s = slide(prs)
    header(s, "14", "团队、开发计划与在芜落地", "创客个人参赛；已完成本地全链路 MVP，按平台要求迁移")
    textbox(s, 0.7, 1.8, 5.85, 4.4, [
        ("团队能力", {"size": 14, "bold": True, "color": TEAL_DK}),
        ("王同鹤：创客个人，AI 应用全栈开发背景（LLM 工程 / 语音 / 检索 / 政务合规）。", {"size": 11.5, "space_before": 8}),
        ("已独立完成：五节点链路、双引擎转写、政策 RAG、图片证据、合规审查、时限督办、流转看板、wiki、RBAC 与审计，以及全部自动化验证脚本。", {"size": 11.5, "color": MUT, "space_before": 6}),
    ])
    textbox(s, 6.85, 1.8, 5.8, 4.4, [
        ("开发计划", {"size": 14, "bold": True, "color": TEAL_DK}),
        ("复赛期：按极智平台能力迁移核心工作流（五节点 + 知识库 + 人工确认节点），本地系统作为外接测试系统。", {"size": 11.5, "space_before": 8}),
        ("发布：智能体发布到应用商店并保持服务开启，评审期内可用。", {"size": 11.5, "color": MUT, "space_before": 6}),
        ("在芜落地：与 12345 话务中心试点——以回调方式接入脱敏录音灰度试用，按「建议采纳率 / 人工修改率 / 单案耗时」三项指标评估。", {"size": 11.5, "color": MUT, "space_before": 6}),
    ])
    rect(s, 0.7, 6.3, 11.93, 0.6, fill=BG, line=HAIR)
    textbox(s, 0.92, 6.42, 11.5, 0.4, [
        ("合规承诺：智能体不自动派单、不自动向群众发送任何内容；未经人工最终放行不得归档；所有结论标注依据与不确定性。", {"size": 11, "color": TEAL_DK}),
    ])
    footer(s)


def s16_commands(prs):
    s = slide(prs)
    header(s, "15", "附：可复现验证命令清单", "全部在 backend/ 目录下执行（Python 3.11 venv）")
    cmds = [
        "python scripts/eval_classify.py            # 分类留一验证 100%",
        "python scripts/eval_dispatch.py            # 派单对照：三层决策 94.4% vs 通用 5.6%",
        "python scripts/eval_vision.py              # 图片隐患识别（16 张公开许可图集）",
        "python scripts/verify_reply_audit.py       # 答复合规：召回 100% / 误报 0%",
        "python scripts/verify_deadline.py          # 时限计算 12/12",
        "python scripts/verify_pillars.py           # 五支柱服务级验证",
        "python scripts/verify_pillars_e2e.py       # 真实链路端到端（含图片证据升级）",
        "python scripts/verify_flow.py              # 流转状态机（含角色守卫、非法迁移拒绝）",
        "python scripts/verify_rbac.py              # 轻量 RBAC（启用态 12/12）",
        "python scripts/verify_wiki.py              # 知识词条（含案件沉淀）",
        "python scripts/verify_cross_check.py       # 双模型交叉复核与分歧统计",
        "pytest tests -q                            # 单元测试",
    ]
    textbox(s, 0.7, 1.75, 11.93, 5.0, [(c, {"size": 11.5, "color": INK, "line_spacing": 1.5}) for c in cmds])
    footer(s)


def main() -> int:
    prs = new_deck()
    s01_cover(prs)
    s02_agenda(prs)
    s03_scene(prs)
    s04_competition(prs)
    s05_architecture(prs)
    s06_dispatch(prs)
    s07_urgency(prs)
    s08_vision(prs)
    s09_reply_audit(prs)
    s10_trust(prs)
    s11_flow_wiki(prs)
    s12_data_model(prs)
    s13_results(prs)
    s14_demo(prs)
    s15_plan(prs)
    s16_commands(prs)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"已生成：{OUT}（{len(prs.slides)} 页，{OUT.stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
