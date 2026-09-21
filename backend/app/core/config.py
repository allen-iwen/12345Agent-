"""应用配置：从 backend/.env 读取（pydantic-settings）。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"

    # 大模型（OpenAI 兼容接口，默认 DeepSeek；实验可切本地 vLLM 服务）
    llm_api_key: str = "replace_me"
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"
    # 本地实验引擎（vLLM 部署 Qwen）可能不支持 response_format=json_object，
    # 置 false 后依赖 _extract_json 宽松解析（含裸换行修复）
    llm_json_mode: bool = True
    # 关闭模型内置思考链（Qwen 系 chat_template_kwargs.enable_thinking=false），
    # DeepSeek 推理模型忽略此开关
    llm_disable_thinking: bool = False

    # 科大讯飞录音文件转写（第二阶段）
    kdsf_asr_app_id: str = "replace_me"
    kdxs_asr_access_key_id: str = "replace_me"

    # 科大讯飞 WebSocket 语音听写 v2（云端 ASR 首选引擎）
    xf_asr_app_id: str = ""
    xf_asr_api_secret: str = ""
    xf_asr_api_key: str = ""

    # 数据与存储路径
    data_dir: Path = BACKEND_ROOT / "data"
    storage_dir: Path = BACKEND_ROOT / "storage"
    sqlite_path: Path = BACKEND_ROOT / "storage" / "cases.sqlite3"
    processed_orders_path: Path = BACKEND_ROOT / "data" / "processed" / "work_orders.jsonl"
    category_catalog_path: Path = BACKEND_ROOT / "data" / "categories" / "category_catalog.json"
    department_rules_path: Path = BACKEND_ROOT / "data" / "departments" / "department_rules.json"

    # 运营商/呼叫中心对接（真实政务热线接入；详见 docs/telephony.md）
    telephony_provider: str = "generic"  # generic（回调/目录投递）| sip（FreeSWITCH 规划位）
    telephony_webhook_secret: str = ""  # 回调鉴权，生产必配；空=放行并告警（联调）
    telephony_recording_dir: Path = BACKEND_ROOT / "storage" / "telephony_recordings"

    # ---- 多模态视觉（图片证据受理）----
    # MiniMax OpenAI 兼容接口：POST {base}/v1/chat/completions，content 支持 image_url（URL 或 data URL）
    vision_provider: str = "none"  # minimax | qianfan | none
    vision_base_url: str = "https://api.minimaxi.com/v1"
    vision_api_key: str = ""
    vision_model: str = "MiniMax-M3"
    # 备用 provider（主 provider 不可用时自动降级）
    vision_fallback_provider: str = ""
    vision_fallback_base_url: str = ""
    vision_fallback_api_key: str = ""
    vision_fallback_model: str = ""
    vision_timeout_s: int = 30
    attachment_dir: Path = BACKEND_ROOT / "storage" / "attachments"

    # ---- 第二模型交叉复核（默认关闭；评测/演示开启）----
    llm_review_enabled: bool = False
    llm_review_model: str = ""
    llm_review_base_url: str = ""
    llm_review_api_key: str = ""

    # ---- 轻量 RBAC 与审计 ----
    # True 时对关键写操作强制鉴权；开发态可置 False 保持无感
    rbac_enabled: bool = False
    session_secret: str = ""  # 空则启动时生成临时密钥并告警
    session_ttl_hours: int = 12
    # 首次启动创建管理员时使用的密码；留空则生成随机密码并打印到控制台（仅一次）
    auth_bootstrap_password: str = ""

    # ---- 办理时限 ----
    deadline_workdays_only: bool = True  # 是否按工作日计算一般件时限
    holidays_path: Path = BACKEND_ROOT / "data" / "dispatch" / "holidays.json"

    # ---- System One 决策模型：用带类型的校准概率做判断 ----
    # 契约：POST {base}/v1/systemone  {state, model, questions} → {model, answers{概率}, usage}
    # 获取 Key：typesafe.ai 候补名单（console.typesafe.ai → API Keys）；亦经 Vercel AI Gateway（typesafe-ai/jev）
    decision_provider: str = "none"  # laya（本地开源）| typesafe | vercel | none
    decision_base_url: str = "https://api.typesafe.ai"
    decision_api_key: str = ""
    decision_model: str = "jev-latest"
    decision_timeout_s: int = 20
    decision_enabled: bool = False  # 是否让决策模型参与链路判断（关闭时完全走现有逻辑）
    decision_high_conf: float = 0.9  # ≥ 高阈值：可直接采用
    decision_low_conf: float = 0.5  # < 低阈值：转人工判断（不采用）
    # laya（Apache 2.0 开源、非自回归 System 1 决策模型）本地部署参数
    decision_model_path: str = ""  # 本地目录或仓库 id；空则用默认仓库 + subfolder
    decision_laya_subfolder: str = "multilingual"  # 中文场景必须用 multilingual（根检查点仅英文）
    decision_laya_device: str = "cpu"  # cpu | cuda
    # 选项 token 预算：官方指出高基数 Choice 会因每选项 token 不足而失准，可上调（0=用默认 256）
    decision_laya_head_max_len: int = 0
    decision_laya_max_len: int = 0


@lru_cache
def get_settings() -> Settings:
    return Settings()
