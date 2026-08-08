from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM — gpt-4o-mini cho MOI tac vu (xem specs/chatbot-rag-design.md muc 2), khong doi
    # model dat hon tru khi eval/ cho thay accuracy < 85%.
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Database — PostgreSQL + pgvector (ADR-0008), KHONG dung vector DB rieng.
    database_url: str = "postgresql://vmec:vmec@localhost:5432/vmec04"


@lru_cache
def get_settings() -> Settings:
    return Settings()
