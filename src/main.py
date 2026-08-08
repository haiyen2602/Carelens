from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.chat_routes import chat_router
from src.api.routes import router
from src.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    # TEMP AUTH GATE (chatbot-rag-design.md muc 10 #10) - retire khi auth-api
    # that co. `get_settings()` o tren DA raise (fail-closed that, xem
    # src/config.py::_internal_auth_secret_must_be_configured) neu
    # INTERNAL_AUTH_SECRET chua duoc cau hinh - toi duoc dong nay nghia la
    # da co gia tri that, khong can kiem tra lai o day.
    #
    # KHONG dung dau tieng Viet/emoji trong cac dong print() o day (phat
    # hien 2026-08-08: print() unicode ra console Windows mac dinh code
    # page cp1252 se CRASH ngay luc khoi dong app, khong phai loi hiem -
    # day chinh la moi truong dev cua du an nay). Dung ASCII thuan, giong
    # quy uoc comment/docstring da dung xuyen suot repo.
    print("[INFO] TEMP AUTH GATE - INTERNAL_AUTH_SECRET da cau hinh. Nho retire khi auth-api that co (muc 10 #10).")
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
