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


@lru_cache
def get_settings() -> Settings:
    return Settings()
