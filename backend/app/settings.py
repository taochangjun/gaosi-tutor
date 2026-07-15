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
    # Hugging Face 下载端点（国内默认走 hf-mirror；官方为 https://huggingface.co）
    hf_endpoint: str = "https://hf-mirror.com"
    # Cross-Encoder 精排模型（fastembed TextCrossEncoder；RERANK_PROVIDER=local 时用）
    rag_rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    # 精排后端：local | zhipu | off（docs/rag-rerank-exercise.md 练习 7）
    rerank_provider: str = "local"
    # 智谱 Rerank API（RERANK_PROVIDER=zhipu）
    zhipu_api_key: str = ""
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_rerank_model: str = "rerank"

    _BACKEND_DIR = Path(__file__).resolve().parent.parent
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / "config" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def configure_hf_endpoint() -> str:
    """
    让 huggingface_hub / fastembed 走国内镜像（须在首次下载模型前调用）。

    - HF_ENDPOINT：默认 https://hf-mirror.com（国内镜像）
    - HF_HUB_DISABLE_XET=1：关闭 Xet 传输；镜像下 Xet 常导致 SSL/元数据失败
    """
    import os

    settings = get_settings()
    endpoint = (settings.hf_endpoint or "").rstrip("/") or "https://hf-mirror.com"
    os.environ["HF_ENDPOINT"] = endpoint
    # 未显式配置时默认关闭 Xet（设为 "0" 可重新开启）
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    return endpoint


def get_llm_model() -> str:
    s = get_settings()
    return s.deepseek_model or s.deepseek_model_flash or "deepseek-chat"
