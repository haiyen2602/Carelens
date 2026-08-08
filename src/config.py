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

    # Retrieval (specs/chatbot-rag-design.md muc 4) — gia tri de xuat, CHUA CHOT
    # (can do phan phoi that tren tap out-of-domain o Phase 7, xem build-kickoff-prompt.md muc 4).
    rrf_k: int = 60
    retrieval_top_k: int = 5
    nguong_vector: float = Field(default=0.5, description="TODO: chua chot, can do thuc nghiem")
    nguong_lexical: float = Field(default=0.3, description="TODO: chua chot, can do thuc nghiem")

    # RAO CAN TAM cho /api/v1/chat (chatbot-rag-design.md muc 10 #10 - RUI RO
    # BAO MAT CHAN PRODUCTION, khong phai CAN CHOT can PM duyet - day chi la
    # bien phap giam nhe ky thuat) - KHONG PHAI auth that (khong biet request
    # tu ai, chi biet co dung 1 chuoi bi mat hay khong). Gia tri mac dinh
    # duoi day CHI dung cho local dev/test (ro rang khong phai bi mat that) -
    # BAT BUOC dat INTERNAL_AUTH_SECRET that qua env var cho bat ky moi
    # truong nao chia se ngoai may ca nhan. XOA dependency nay (src/api/
    # security.py::require_internal_secret) khoi route NGAY khi auth-api
    # (JWT that) duoc xay - day la rao can tam, khong phai giai phap cuoi.
    internal_auth_secret: str = Field(
        default="unset-temp-auth-gate-CHANGE-ME-for-any-shared-env",
        description="TEMP: xem chatbot-rag-design.md muc 10 #10, retire khi auth-api that co",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
