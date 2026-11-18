from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
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

    tenant_api_keys: dict[str, SecretStr] = Field(default_factory=dict)
    mcp_tenant: str | None = None

    @field_validator("tenant_api_keys")
    @classmethod
    def validate_keys(cls, value: dict[str, SecretStr]) -> dict[str, SecretStr]:
        keys = [secret.get_secret_value() for secret in value.values()]
        if (
            any(not tenant.strip() for tenant in value)
            or any(len(key) < 32 for key in keys)
            or len(keys) != len(set(keys))
        ):
            raise ValueError("chaves por cliente devem ser únicas e ter pelo menos 32 caracteres")
        return value

    llm_provider: str = "scripted"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = Field(default="", repr=False)
    llm_model: str = "gpt-4o-mini"
    llm_max_output_tokens: int = Field(default=2048, ge=128, le=16384)

    embedding_provider: str = "hashing"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = Field(default="", repr=False)
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=512, ge=1, le=2000)

    database_url: str = Field(default="", repr=False)
    audit_db_path: Path = Path("var/audit.db")
    knowledge_base_dir: Path = Path("data/knowledge_base")
    tickets_history_path: Path = Path("data/tickets_history.jsonl")

    retrieval_top_k: int = Field(default=4, ge=1, le=20)
    retrieval_min_score: float = Field(default=0.12, ge=0, le=1)
    confidence_threshold: float = Field(default=0.6, ge=0, le=1)
    max_agent_steps: int = Field(default=4, ge=2, le=10)
    daily_token_budget_per_tenant: int = Field(default=200_000, ge=1)
    price_table: dict[str, tuple[float, float]] = DEFAULT_PRICES


@lru_cache
def get_settings() -> Settings:
    return Settings()
