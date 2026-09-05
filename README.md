 

# 12345 热线工单智能生成与转派辅助智能体

本项目用于开发“12345 热线工单智能生成与转派辅助智能体”，基础闭环为：录音或文本输入 → 诉求理解与要素确认 → 标准化工单生成 → 事项分类与承办单位推荐 → 人工审核 → 处理结果录入 → 回复与回访话术辅助。

系统只提供辅助建议，最终工单内容、转派结果和群众回复必须由工作人员审核确认。

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

## 工单智能体工作台

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

1. 左栏「受理新诉求」：支持 **录音上传**（本地 SenseVoice 转写，无需外部 API）、文本录入（Ctrl+Enter 提交）、六类演示案例一键填充；
2. 主区顶部是 **流水线轨道**（理解 → 工单 → 分类 → 转派 → 答复），每个节点随审核状态变色，**点击任一节点打开轨迹抽屉**，白盒查看该节点每次执行的输入 / 输出 / 耗时；
3. **工单质量检查**面板：10 项规则校验（要素完整性/分类置信度/职责边界/政策引用真实性等），warn 不阻断但提示人工关注；
4. 右侧四张审核卡片（标准化工单 / 事项分类 / 承办单位 / 答复草拟），每节可「确认」或「修改」（JSON 编辑）；
5. **需人工判断提示**：职责交叉/多类并存/信息不足时，分类与转派卡片显示琥珀色横幅及具体原因；
6. 答复卡片含 **回访参考话术** 与 **政策依据引用**（仅引用 `data/policies/policy_references.json` 中真实存在的公开法规，QC 校验不通过会标警）；
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
| POST | `/api/asr` | 上传录音（multipart）→ 本地 SenseVoice 转写为文本 |
| GET | `/api/runs/cases/{id}` | 该案件全部 Agent 节点轨迹（输入/输出/耗时/状态） |
| GET | `/api/knowledge/orders` | 官方历史工单（`q`/`category` 过滤） |
| GET | `/api/knowledge/categories` | 12 大类目录 |
| GET | `/api/knowledge/search` | BM25 相似工单检索（`text`/`top_k`） |
| GET | `/api/knowledge/stats` | 热点统计（类别分布 / 紧急 / 重复 / 归档） |
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

### 第二阶段：科大讯飞录音转写

`.env` 预留了 `KDXF_ASR_*` 字段（`APP_ID` / `ACCESS_KEY_ID` / `ACCESS_KEY_SECRET`），办完讯飞开放平台的实名认证和免费试用后即可接入。接入时可在 `app/agents/` 下新增一个 `transcribe.py` 节点，把录音 URL 转写为文本后再走理解节点。
