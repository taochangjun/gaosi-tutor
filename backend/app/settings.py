from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_model_flash: str = ""  # 兼容从 MES 复制的 .env
    database_url: str = (
        "mysql+pymysql://root:root1234@127.0.0.1:3306/gaosi_tutor?charset=utf8mb4"
    )
    # --- RAG（家庭笔记向量检索，见 app/agent/rag/）---
    rag_chroma_path: str = "data/chroma"  # Chroma 持久化目录（相对 backend/）
    rag_embedding_model: str = "BAAI/bge-small-zh-v1.5"  # fastembed 模型名；更换须全量 reindex
    rag_top_k: int = 3  # search_family_notes 默认返回条数

    _BACKEND_DIR = Path(__file__).resolve().parent.parent
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / "config" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def get_llm_model() -> str:
    s = get_settings()
    return s.deepseek_model or s.deepseek_model_flash or "deepseek-chat"
