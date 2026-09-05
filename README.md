 

# 12345 热线工单智能生成与转派辅助智能体

本项目用于开发“12345 热线工单智能生成与转派辅助智能体”，基础闭环为：录音或文本输入 → 诉求理解与要素确认 → 标准化工单生成 → 事项分类与承办单位推荐 → 人工审核 → 处理结果录入 → 回复与回访话术辅助。

系统只提供辅助建议，最终工单内容、转派结果和群众回复必须由工作人员审核确认。

## 真实政务热线接入（运营商/呼叫中心对接）

语音入口面向真实部署预留了标准对接层，通话音频到达即自动完成“转写 → 降噪整理 → 五节点建单”，坐席在 Web 工作台直接审核：

- **方式 A · HTTP 回调**：`POST /api/telephony/webhook/call-event`（挂机事件携带录音 URL，支持 http(s) 或政务内网共享盘路径；`X-Telephony-Secret` 鉴权；状态查询 `GET /api/telephony/calls/{call_id}`）
- **方式 B · 录音目录投递**：呼叫平台投放录音至约定目录，`python scripts/telephony_watcher.py` 常驻轮询自动建单
- **方式 C · SIP 中继**（规划位）：政府侧已有 PBX（FreeSWITCH）时经 ESL 对接，配置字段已预留

配置见 `backend/.env.example` 的 `TELEPHONY_*` 段；联调步骤、curl 示例与自检清单见 **[docs/telephony.md](docs/telephony.md)**。已用 6 分钟真实来电录音全链路验证（webhook → 讯飞 9 段转写 → 降噪 → 建单待审）。

## 项目结构

```text
12345agent/
├─ activate_backend_venv.bat      # Windows：激活 backend venv 并启动后端
├─ activate_backend_venv.command  # macOS：双击激活 venv 并启动后端
├─ activate_frontend_venv.bat     # Windows：启动前端开发服务器
├─ activate_frontend_venv.command # macOS：双击启动前端开发服务器
├─ backend/                       # Python、FastAPI、LangGraph、数据与测试
│  ├─ app/
│  │  ├─ api/
│  │  │  └─ routes/              # FastAPI 路由与请求入口
│  │  ├─ agents/                 # Agent 节点、工具调用与模型逻辑
│  │  ├─ core/                   # 配置、日志和通用基础能力
│  │  ├─ repositories/           # SQLite、向量库等数据访问
│  │  ├─ schemas/                # Pydantic 输入、输出与状态模型
│  │  ├─ services/               # 业务服务与模块编排
│  │  ├─ workflow/               # LangGraph 状态与工作流
│  │  └─ main.py                 # FastAPI 应用入口
│  ├─ data/
│  │  ├─ categories/             # 事项分类目录（category_catalog.json）
│  │  ├─ departments/            # 承办单位职责规则（department_rules.json）
│  │  ├─ mock/                   # Mock 请求（mock_requests.json）与期望结果
│  │  ├─ processed/              # 数据准备脚本生成结果
│  │  ├─ raw/official_work_orders/  # 官方 Excel 与配套录音本机副本
│  │  └─ README.md               # 数据目录说明
│  ├─ scripts/                   # 数据准备和维护脚本（prepare_dataset.py）
│  ├─ storage/                   # SQLite、上传文件等本机运行数据
│  ├─ tests/                     # 后端自动化测试（test_health.py）
│  ├─ .env.example               # 后端环境变量模板，不含真实密钥
│  ├─ requirements.txt           # Python 后端依赖
│  ├─ verify_env.py              # 后端环境检查
│  ├─ check_deepseek.py          # DeepSeek 最小连通性检查（手动执行）
│  └─ README.md                  # 后端工程说明
├─ frontend/                     # React + TypeScript + Vite 前端工程
│  ├─ public/                    # 静态资源（favicon.svg、icons.svg）
│  ├─ src/
│  │  ├─ assets/                 # 图片等静态资源
│  │  ├─ App.tsx                 # 根组件（当前为 Vite 模板页）
│  │  ├─ App.css
│  │  ├─ main.tsx                # 前端入口
│  │  └─ index.css
│  ├─ index.html                 # HTML 模板
│  ├─ .env.example               # 前端非敏感环境变量模板
│  ├─ package.json               # 前端依赖与脚本
│  ├─ package-lock.json          # 前端依赖锁定文件
│  ├─ vite.config.ts             # Vite 配置
│  ├─ tsconfig.json              # TypeScript 基础配置
│  ├─ tsconfig.app.json          # 应用 TS 配置
│  ├─ tsconfig.node.json         # 节点侧 TS 配置
│  ├─ eslint.config.js           # ESLint 配置
│  └─ README.md                  # 前端工程说明
├─ .gitignore                     # 全仓库通用忽略规则
└─ README.md                      # 项目总说明
```

## 后端快速开始

先从仓库根目录进入 `backend/`，用标准库 `venv` 构建 Python 虚拟环境，激活后再安装依赖并启动：

```powershell
cd backend
# 1. 构建 Python 虚拟环境（仅在首次或环境缺失时执行）
python -m venv venv
# Windows 激活虚拟环境：
venv\Scripts\activate
# macOS / Linux 激活虚拟环境：
source venv/bin/activate
# 2. 安装依赖、检查环境、运行测试与启动服务
python -m pip install --upgrade pip setuptools wheel #安装基础工具
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ #安装依赖
```

初次构建依赖后执行：

```PowerShell
# 验证环境是否构建完成
Copy-Item .env.example .env
python verify_env.py
```

后端服务启动

```PowerShell
cd backend
venv\Scripts\activate
python -m uvicorn app.main:app --reload
```


启动后访问：

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

后端的 `.env`、依赖和运行命令均以 `backend/` 为工作目录。详细说明见 `backend/README.md`。

## 前端快速开始

前端已初始化为 React + TypeScript + Vite 工程。首次使用时从仓库根目录执行：

```powershell
cd frontend
npm install #前端依赖安装
npm run build #生产构建检查
```

前端服务启动

```PowerShell
cd frontend
npm run build
```

启动后访问 Vite 输出的本地地址，通常是：

- `http://localhost:5173`

前端只允许保存 `VITE_API_BASE_URL` 等非敏感配置，真实模型密钥不得写入前端代码或前端环境变量。



## 初始数据准备

1. 下载官方数据集：[12345赛题数据集-信件类别示例工单及录音.zip](https://pan.baidu.com/s/1ysOOYqmoAQTr_yJWQLXoyw?pwd=u9ca)，提取码：u9ca。

2. 打开官方数据集并解压，查看其中的 '信件类别示例工单及录音' 文件夹。
3. 将  '信件类别示例工单及录音' 文件夹 中的所有文件全部复制到项目的 项目的  `backend\data\raw\official_work_orders` 目录中。
4. 执行以下命令：

```powershell
cd backend
# Windows 激活环境
.\venv\Scripts\Activate.ps1

# macOS 激活环境
source venv/bin/activate

python scripts/prepare_dataset.py data/raw/official_work_orders
```





## 数据安全

官方 Excel 与配套录音按类别放入 `backend/data/raw/official_work_orders/`。当前 `prepare_dataset.py` 只匹配并处理 Excel，不会打开、转写或分析录音。

真实密钥只写入 `backend/.env`，不得提交 Git。真实姓名、手机号、身份证号、详细地址、未经授权的录音和未脱敏工单不得进入公开仓库。

### 双引擎语音转写（讯飞云端优先，本地兜底）

录音上传优先走 **科大讯飞 WebSocket 语音听写 v2**（`app/services/xf_asr.py`）：HMAC-SHA256 鉴权、16k PCM 分帧、静音感知分段（单连接 60s 上限，长音频在 35–55s 窗口内寻找静音点切分）、wpgs 动态修正帧组装（实测修正帧以标点开头携带纠错全文，按前缀+后缀重叠度与回溯合并去重）。6 分钟真实来电约 40–60s 完成转写，带标点、自动纠错。云端异常时自动降级本地 SenseVoice，响应标注引擎来源与耗时。

转写整理前置**领域词典确定性纠错**（`data/asr/domain_lexicon.json`）：芜湖区划地名（镜糊区→镜湖区、万止区→湾沚区等）、部门、高频诉求词（印井盖→窨井盖、非线充电→飞线充电、夜化气→液化气）的同音近音误识别在 LLM 降噪前被逐条替换，每处命中计入白盒 changes 报告，原始转写不动（证据保全）。

### 分类与识别准确率评测（可复现）

- **分类**：`scripts/eval_classify.py` 对 18 条官方历史工单做**留一交叉验证**（LOO，few-shot 池排除测试样本自身防答案泄漏）。基线（目录仅 code+name）**72.2%（13/18）**；为 12 类补充"定义/典型情形/易混淆辨析"（`data/categories/category_catalog.json`，如"培训机构退费归科教文体而非市场监管""宅基地审批归农林水土而非城乡建设""消防设施归公共安全而非城市管理"）后 **100%（18/18）**，边界错例全部翻正，平均置信度同步提升。
- **识别纠错**：`scripts/test_lexicon.py` 覆盖区划/部门/诉求词三类确定性替换（5/5 通过），正常文本零误替换。

### 政策依据 RAG（可上传，防虚构引用）

- 内置 8 份真实公开法规（`data/policies/policy_references.json`）；
- 支持上传 PDF / DOCX / TXT / MD / JSON 政策文件（≤20MB），切分向量化入 Chroma（bge-small-zh-v1.5 嵌入），知识库页可管理、可删除；
- 回答节点引用"精选法规 + RAG 检索命中"的来源名，**QC 校验引用真实性**（不在库中的引用标警），防止模型虚构法条；
- 检索接口 `GET /api/policies/search?q=...`。

### 未诉先办 · 苗头预警（创新点）

同点位（地点线索字滑窗公共子串）+ 同分类诉求在 7 日内聚集 ≥3 件时，案件详情顶部出现「未诉先办 · 苗头预警」横幅，列出同源案件清单，建议并案核查、转主动治理工单——呼应国办发〔2020〕53 号推广"接诉即办"后向"未诉先办"深化的治理方向，把群体性矛盾化解在扩散之前。

### 基层减负账本

白盒轨迹逐案累计智能体耗时，对比人工工序基准（要素核对与工单规范化 8′ + 分类转派比对 4′ + 答复草拟 8′，约 20 分钟/件，估算值）：案件页显示"本案约节省 X 分钟"，知识库统计页显示全局累计（实测每案智能体 1–2 分钟 vs 人工 20 分钟）。

### 工单智能体工作台

本项目后端实现了「诉求理解 → 标准化工单生成 → 事项分类 → 承办单位推荐 → 回复建议」全链路，所有结果仅供辅助，最终工单内容、转派结果和群众回复必须由工作人员审核确认。

### 启动顺序

```powershell
# 终端 1：后端（端口 8000）
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 终端 2：前端（端口 5173）
cd frontend
npm run dev
```

浏览器打开 `http://localhost:5173` 即可使用工作台：

1. 左栏「受理新诉求」：支持 **录音上传**（双引擎：讯飞云端优先，本地 SenseVoice 兜底；响应显示引擎来源/耗时/段数）、文本录入（Ctrl+Enter 提交）、六类演示案例一键填充；
2. 主区顶部是 **流水线轨道**（理解 → 工单 → 分类 → 转派 → 答复），每个节点随审核状态变色，**点击任一节点打开轨迹抽屉**，白盒查看该节点每次执行的输入 / 输出 / 耗时；
3. **工单质量检查**面板：10 项规则校验（要素完整性/分类置信度/职责边界/政策引用真实性等），warn 不阻断但提示人工关注；
4. 右侧四张审核卡片（标准化工单 / 事项分类 / 承办单位 / 答复草拟），每节可「确认」或「修改」（JSON 编辑）；
5. **需人工判断提示**：职责交叉/多类并存/信息不足时，分类与转派卡片显示琥珀色横幅及具体原因；
6. 答复卡片含 **回访参考话术** 与 **政策依据引用**（精选法规 ∪ RAG 已入库文档，QC 校验真实性，省略版本括注的法规短名亦可通过）；
7. 左下「相似官方工单」面板基于 BM25 检索 18 条官方样例，可一键复制官方答复口径；
8. 原始诉求卡内可录入回访补充信息，触发全链路重跑；
9. 四节审核完成后，底部「最终放行 · 归档」亮起，点击后案件完成；
10. 顶栏「知识库」页：官方历史工单浏览（分类过滤 + 全文检索）+ **热点统计**（官方样例与本系统受理的类别分布对比）。

### 政策依据库

`backend/data/policies/policy_references.json` 收录国办发〔2020〕53号、《噪声污染防治法》《物业管理条例》《市容和环境卫生管理条例》《消费者权益保护法》《保障农民工工资支付条例》《医疗保障基金使用监督管理条例》《道路交通安全法》共 8 份真实公开法规。回复节点仅可引用库内文件（prompt 强约束 + QC 双重校验），来源为公开法规库，使用范围见文件内说明。

### API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/cases` | 录入诉求文本，启动全链路 |
| GET | `/api/cases` | 案件列表（最近 30 条） |
| GET | `/api/cases/{id}` | 案件详情（含各节产物 + 审核状态 + QC 检查） |
| POST | `/api/cases/{id}/review` | 分节 `approve`/`modify`；`section=final` + `approve` 触发工作流 resume |
| POST | `/api/cases/{id}/clarify` | 补充市民信息后重跑链路（用新 thread_id，保留历史 checkpoint） |
| POST | `/api/asr` | 上传录音（multipart）→ 双引擎转写（讯飞云端优先，SenseVoice 兜底） |
| GET | `/api/asr/status` | ASR 引擎配置状态 |
| POST | `/api/policies` | 上传政策文件入 RAG 库（multipart，≤20MB） |
| GET | `/api/policies` | 已入库文档列表 |
| DELETE | `/api/policies/{upload_id}` | 删除已入库文档 |
| GET | `/api/policies/search` | 政策语义检索（`q`/`top_k`） |
| GET | `/api/runs/cases/{id}` | 该案件全部 Agent 节点轨迹（输入/输出/耗时/状态） |
| GET | `/api/knowledge/orders` | 官方历史工单（`q`/`category` 过滤） |
| GET | `/api/knowledge/categories` | 12 大类目录 |
| GET | `/api/knowledge/search` | BM25 相似工单检索（`text`/`top_k`） |
| GET | `/api/knowledge/stats` | 热点统计（类别分布 / 紧急 / 重复 / 归档 / 减负账本） |
| GET | `/health`、`/docs` | 健康检查 + Swagger 文档 |

### 检索与提示词要点

- 事项分类、承办单位推荐、回复建议三个节点通过 `rank-bm25` 检索 `data/processed/work_orders.jsonl` 中的相似官方工单作为参考；
- 12 大类目录在 `data/categories/category_catalog.json`，承办单位职责规则在 `data/departments/department_rules.json`（未录入时回退到历史工单参考）；
- 紧急/危险诉求（燃气泄漏、火灾、人身安全等）会被 `urgent=true` 标记，Agent 在 `manual_action` 中提示工作人员紧急处置，并明确"Agent 不替代报警或应急指挥"。

### 自动化测试

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m pytest -v
```

- `tests/test_workflow.py` 用桩 LLM 跑完整链路（无需真实 API），验证 5 节点全部产出、`final` 放行可 resume 至完成；
- `tests/test_health.py` 验证 `/health` 接口。

`backend/scripts/api_e2e.py` 是真实链路冒烟脚本，串一遍创建→分节审→改→最终放行的全流程。

`backend/scripts/acceptance_full.py` 是**全链路真实验收**（31 项断言，需真实密钥与官方录音数据）：健康检查 / 知识库与 BM25 / 讯飞云端转写真实录音 / 紧急件全生命周期（分节审核→修改→放行）/ 澄清补录重跑 / 苗头预警触发 / 政策 RAG 上传-检索-删除 / 减负账本 / 白盒轨迹耗时。最近一次运行 **31/31 通过**。
