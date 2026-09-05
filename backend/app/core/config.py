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

    # 大模型（OpenAI 兼容接口，默认 DeepSeek）
    llm_api_key: str = "replace_me"
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
