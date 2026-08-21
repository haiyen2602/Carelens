from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.account_routes import account_router
from backend.api.admin_drug_routes import admin_drug_router
from backend.api.auth_routes import auth_router
from backend.api.caregiver_routes import caregiver_router
from backend.api.chat_routes import chat_router
from backend.api.dose_routes import dose_router
from backend.api.drug_request_routes import admin_drug_request_router, drug_request_router
from backend.api.drug_routes import drug_router
from backend.api.escalation_routes import escalation_router
from backend.api.health_log_routes import health_log_router
from backend.api.nudge_routes import nudge_router
from backend.api.patient_routes import patient_router
from backend.api.photo_routes import photo_router
from backend.api.prescription_routes import prescription_router
from backend.api.rag_monitoring_routes import rag_monitoring_router
from backend.api.reporting_routes import reporting_router
from backend.api.routes import router
from backend.config import get_settings
from backend.services.drug_knowledge.v2_agent import warm_v2_agent_knowledge_service
from backend.services.escalation_scheduler import start_escalation_scheduler, stop_escalation_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    # TEMP AUTH GATE (chatbot-rag-design.md muc 10 #10) - retire khi auth-api
    # that co. `get_settings()` o tren DA raise (fail-closed that, xem
    # backend/config.py::_internal_auth_secret_must_be_configured) neu
    # INTERNAL_AUTH_SECRET chua duoc cau hinh - toi duoc dong nay nghia la
    # da co gia tri that, khong can kiem tra lai o day.
    #
    # KHONG dung dau tieng Viet/emoji trong cac dong print() o day (phat
    # hien 2026-08-08: print() unicode ra console Windows mac dinh code
    # page cp1252 se CRASH ngay luc khoi dong app, khong phai loi hiem -
    # day chinh la moi truong dev cua du an nay). Dung ASCII thuan, giong
    # quy uoc comment/docstring da dung xuyen suot repo.
    print("[INFO] TEMP AUTH GATE - INTERNAL_AUTH_SECRET da cau hinh. Nho retire khi auth-api that co (muc 10 #10).")

    if settings.drug_knowledge_backend in ("v2", "shadow"):
        warmup = warm_v2_agent_knowledge_service()
        print(
            "[INFO] Drug Knowledge V2 warmup complete: "
            f"products={warmup['products']} chunks={warmup['chunks']} duration_ms={warmup['duration_ms']:.2f}"
        )

    # Vong 2, muc 13 (chatbot-rag-design.md) - scheduler nhac lai escalation.
    # SQLAlchemyJobStore (khong in-memory) - xem docstring escalation_scheduler.py.
    start_escalation_scheduler()
    print("[INFO] Escalation reminder scheduler started.")

    yield

    stop_escalation_scheduler()
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
app.include_router(auth_router, prefix="/api/v1")
app.include_router(account_router, prefix="/api/v1")
app.include_router(admin_drug_router, prefix="/api/v1")
app.include_router(drug_request_router, prefix="/api/v1")
app.include_router(admin_drug_request_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(escalation_router, prefix="/api/v1")
app.include_router(drug_router, prefix="/api/v1")
app.include_router(patient_router, prefix="/api/v1")
app.include_router(prescription_router, prefix="/api/v1")
app.include_router(photo_router, prefix="/api/v1")
app.include_router(dose_router, prefix="/api/v1")
app.include_router(reporting_router, prefix="/api/v1")
app.include_router(caregiver_router, prefix="/api/v1")
app.include_router(rag_monitoring_router, prefix="/api/v1")
app.include_router(nudge_router, prefix="/api/v1")
app.include_router(health_log_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}

# Trigger hot reload for new router additions
