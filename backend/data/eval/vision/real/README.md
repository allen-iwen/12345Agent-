# 城市隐患现场照片视觉评测集（real）

本目录是「12345 政务热线智能体」**图片证据视觉评测**所用的真实隐患照片集与标注集。
仅用于模型评测，**不属于产品素材库**。

## 1. 内容清单

| 文件 | 数量 | 说明 |
| --- | --- | --- |
| `*.jpg` | 16 | 城市隐患现场照片，已统一处理 |
| `labels.json` | — | 标注集（schema_version 1.0），逐张登记预期隐患类型、严重度与来源许可 |
| `README.md` | — | 本文件 |

### 题材分布

| 隐患类型 | 张数 | 文件名 | 严重度 |
| --- | --- | --- | --- |
| 井盖缺失 | 2 | `manhole_missing_01.jpg`、`manhole_missing_02.jpg` | 特急 |
| 道路破损 | 3 | `pothole_road_01.jpg`、`pothole_road_02.jpg`、`pothole_road_03.jpg` | 一般 |
| 垃圾堆积 | 3 | `garbage_dump_01.jpg`、`garbage_dump_02.jpg`、`garbage_dump_03.jpg` | 紧急 |
| 违章建筑 | 2 | `illegal_construction_01.jpg`、`illegal_construction_02.jpg` | 紧急 |
| 占道经营 | 2 | `vendor_sidewalk_01.jpg`、`vendor_sidewalk_02.jpg` | 紧急 |
| 消防通道堵塞 | 1 | `fire_lane_blocked_01.jpg` | 特急 |
| 电线坠落 | 3 | `fallen_wire_01.jpg`、`fallen_wire_02.jpg`、`fallen_wire_03.jpg` | 特急 |
| **合计** | **16** | | |

严重度取值遵循评测规则：存在人身安全隐患（井盖缺失、电线坠落、消防通道堵塞）→ `特急`；
影响面较大但无即时人身危险（垃圾堆积、占道经营、违建）→ `紧急`；仅轻微破损（小坑洼/路面开裂）→ `一般`。

## 2. 来源与许可

全部图片来自 **Wikimedia Commons**（<https://commons.wikimedia.org>）。
要求为 CC0 / 公有领域 / CC BY / CC BY-SA，逐张信息已登记在 `labels.json` 的
`source_page`、`source_url`、`author`、`license`、`license_url` 字段中。

许可分布：CC BY-SA 4.0 × 6、CC0 × 3、CC BY 2.0 × 2、CC BY 3.0 × 2、CC BY-SA 2.0 × 1、
Public domain × 2（`fallen_wire_01`、`fallen_wire_02` 的原始条目，FEMA / NIST 美国联邦政府作品）。

> 关于"Public domain"两条：Commons 元数据的 `LicenseUrl` 为空，因为公有领域是一种权利状态而非许可证文本。
> 因此 `labels.json` 中这两条的 `license_url` 填的是其 Commons 文件描述页，供人工复核使用，
> **它们没有 CC 许可证 URL，再分发前必须自行确认其公有领域依据**。

## 3. 下载日期

**2026-09-20**。来源为 Wikimedia Commons 的公开文件，图片处理流程见下节。

## 4. 处理方式

下载原始文件后统一处理，未做裁剪、拼接或内容修改：

- 等比缩放，最长边 ≤ **1024 px**（`PIL.Image.thumbnail` + LANCZOS）
- 转换为 **JPEG，质量 85**
- 文件名改为英文小写下划线形式（如 `manhole_missing_01.jpg`）

## 5. 隐私筛查

已逐张目视核查，剔除并替换了以下不合规素材：

- 含**可辨认人脸 / 行人清晰正脸**的照片
- 含**可辨认车牌**的照片（已排除两张候选图：New Orleans 街景坑洼图、
  Hurricane Maria 波多黎各断线图——后者画面中车牌可辨识）
- 含**可辨认门牌号**的照片

最终 16 张均未包含可识别的个人面部、车牌或门牌号。

## 6. 使用范围

- ✅ 仅用于本地模型**视觉能力评测**（隐患识别、严重度分级）
- ❌ 不随任何作品、产品、演示或数据集对外再分发
- ❌ 不用于训练、商业宣传、新闻配图

## 7. ⚠️ 再分发提示

> **如需再分发，必须逐张重新核对许可证。**
>
> 本目录中的图片版权归各原作者所有。CC BY / CC BY-SA 要求**署名**，
> CC BY-SA 还要求**衍生作品以相同许可证发布**；CC0 与公有领域图片虽无署名义务，
> 但公有领域依据本身需要复核。
>
> 请注意：本数据集**没有**做上述署名与同许可证义务的落地工作（本目录仅用于评测，
> 不做再分发）。一旦对外发布，请按 `labels.json` 的 `author` / `license` /
> `license_url` 逐条补齐署名与许可证声明。

## 8. 已知取材缺口

**「消防通道堵塞」仅 1 张，覆盖不足**。缺口原因：

- Wikimedia Commons 上以 `blocked fire lane` / `fire hydrant obstructed` / `fire lane`
  等关键词检索，结果绝大多数是**空的消防通道标识牌**（`NO PARKING FIRE LANE` 立牌、
  地面划线、库区消防栓），并不构成"通道被堵塞"的隐患画面；
- 曾有少量候选（美国街头黄线消防通道涂装、手绘消防通道告示牌）因画质过差或
  画面主体并非堵塞而被剔除；
- 未在 Pexels / Unsplash 上补图，因为该两类站点的许可为自定义许可（虽免费商用但非
  CC 系），与本次"公开许可"登记口径不完全一致，为避免许可证信息混淆而未采用。

因此「消防通道堵塞」目前以 1 张**疏散出口被货物完全堵塞**的照片（`fire_lane_blocked_01.jpg`，
中国上海松江，CC0）代表该类别。如需≥2 张，建议后续定向补充
**消防车道被违停车辆占用**类画面。

其余 6 类均达到 2–3 张的要求。

## 9. 校验

使用 PIL 逐张验证可读性、格式与尺寸，并核对 `labels.json` 中每个 `file` 均存在于本目录。
校验脚本见同级 `_work/validate.py`（工作目录，非交付物）。
