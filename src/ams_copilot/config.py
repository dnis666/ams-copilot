from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.00),
    "qwen": (0.0, 0.0),
    "llama": (0.0, 0.0),
    "scripted": (0.0, 0.0),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AMS_", env_file=".env", extra="ignore")

    llm_provider: str = "scripted"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    embedding_provider: str = "hashing"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 512

    database_url: str = ""
    audit_db_path: Path = Path("var/audit.db")
    knowledge_base_dir: Path = Path("data/knowledge_base")
    tickets_history_path: Path = Path("data/tickets_history.jsonl")

    retrieval_top_k: int = 4
    retrieval_min_score: float = 0.12
    confidence_threshold: float = 0.6
    max_agent_steps: int = 4
    daily_token_budget_per_tenant: int = 200_000
    price_table: dict[str, tuple[float, float]] = DEFAULT_PRICES


@lru_cache
def get_settings() -> Settings:
    return Settings()
