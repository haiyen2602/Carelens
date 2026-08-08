from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel PUBLIC (nam trong repo, KHONG phai bi mat that) - dung de PHAT
# HIEN "chua ai dat INTERNAL_AUTH_SECRET that" trong _internal_auth_secret_
# must_be_configured() ben duoi. Chinh vi gia tri nay cong khai trong source
# (va trong .env.example) nen KHONG duoc phep dung lam gia tri chay that -
# validator raise ngay neu con bang gia tri nay, khong chi log roi cho qua.
_UNSET_INTERNAL_SECRET_SENTINEL = "unset-temp-auth-gate-CHANGE-ME-for-any-shared-env"


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
    # tu ai, chi biet co dung 1 chuoi bi mat hay khong). BAT BUOC dat
    # INTERNAL_AUTH_SECRET that qua env var (.env, KHONG commit gia tri that)
    # - fail-closed THAT (xem validator ben duoi), khong chi canh bao roi
    # van chay: neu con la sentinel/rong, Settings() raise NGAY luc doc
    # config (app/test suite khong khoi dong duoc), khong doi toi luc co
    # request that moi phat hien. Ap dung ke ca local dev/test - "chi la
    # local" khong phai ly do mien tru, dung y "phong ve ky thuat dang tin
    # hon tri nho tap the" da thong nhat 2026-08-08. XOA dependency nay
    # (src/api/security.py::require_internal_secret) khoi route NGAY khi
    # auth-api (JWT that) duoc xay - day la rao can tam, khong phai giai
    # phap cuoi.
    internal_auth_secret: str = Field(
        default=_UNSET_INTERNAL_SECRET_SENTINEL,
        description="TEMP: xem chatbot-rag-design.md muc 10 #10, retire khi auth-api that co",
    )

    @field_validator("internal_auth_secret")
    @classmethod
    def _internal_auth_secret_must_be_configured(cls, v: str) -> str:
        if not v or v == _UNSET_INTERNAL_SECRET_SENTINEL:
            raise ValueError(
                "INTERNAL_AUTH_SECRET chua duoc cau hinh that (con rong hoac la sentinel cong khai "
                f"{_UNSET_INTERNAL_SECRET_SENTINEL!r} - gia tri nay NAM SAN TRONG SOURCE nen KHONG "
                "duoc dung de chay that). Dat INTERNAL_AUTH_SECRET trong .env (khong commit gia tri "
                "that) truoc khi khoi dong app hoac chay test - xem chatbot-rag-design.md muc 10 #10."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
