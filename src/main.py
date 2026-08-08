from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.chat_routes import chat_router
from src.api.routes import router
from src.config import get_settings

_UNSET_INTERNAL_SECRET_DEFAULT = "unset-temp-auth-gate-CHANGE-ME-for-any-shared-env"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    # TEMP AUTH GATE (chatbot-rag-design.md muc 10 #10) - retire khi auth-api
    # that co. Canh bao ro rang luc khoi dong de KHONG AI vo tinh chay o moi
    # truong chia se ma quen dat INTERNAL_AUTH_SECRET that qua env var.
    #
    # KHONG dung dau tieng Viet/emoji o day (phat hien 2026-08-08: print()
    # unicode ra console Windows mac dinh code page cp1252 se CRASH ngay
    # luc khoi dong app, khong phai loi hiem - day chinh la moi truong dev
    # cua du an nay). Dung ASCII thuan, giong quy uoc comment/docstring da
    # dung xuyen suot repo, khong phai chi tieng Viet co dau -> khong dau.
    if settings.internal_auth_secret == _UNSET_INTERNAL_SECRET_DEFAULT:
        print(
            "[WARNING] TEMP AUTH GATE - INTERNAL_AUTH_SECRET chua duoc cau hinh "
            "(van la gia tri mac dinh local dev). /api/v1/chat KHONG duoc de moi "
            "truong chia se/demo chay voi gia tri nay - xem chatbot-rag-design.md "
            "muc 10 #10. Retire dependency nay khi auth-api (JWT) that co."
        )
    else:
        print(
            "[INFO] TEMP AUTH GATE - INTERNAL_AUTH_SECRET da cau hinh. "
            "Nho retire khi auth-api that co (chatbot-rag-design.md muc 10 #10)."
        )
    yield
    print("Shutting down...")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
