import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.account_routes import account_router
from backend.api.admin_drug_routes import admin_drug_router
from backend.api.admin_feedback_routes import admin_feedback_router
from backend.api.admin_monitoring_routes import admin_monitoring_router
from backend.api.admin_safety_routes import admin_safety_router
from backend.api.agent_feedback_routes import agent_feedback_router
from backend.api.agent_v2_routes import agent_v2_router
from backend.api.audit_routes import audit_router, my_audit_router
from backend.api.auth_routes import auth_router
from backend.api.caregiver_routes import caregiver_router
from backend.api.chat_routes import chat_router
from backend.api.doctor_review_routes import doctor_review_router, patient_handoff_router
from backend.api.dose_routes import dose_router
from backend.api.drug_image_chat_routes import drug_image_chat_router, get_drug_image_recognizer
from backend.api.drug_image_routes import drug_image_router
from backend.api.drug_request_routes import admin_drug_request_router, drug_request_router
from backend.api.drug_routes import drug_router
from backend.api.escalation_routes import escalation_router
from backend.api.health_log_routes import health_log_router
from backend.api.notification_routes import notification_router
from backend.api.nudge_routes import nudge_router
from backend.api.patient_routes import patient_router
from backend.api.photo_routes import photo_router
from backend.api.prescription_routes import prescription_router
from backend.api.push_routes import push_router
from backend.api.rag_monitoring_routes import rag_monitoring_router
from backend.api.reporting_routes import reporting_router
from backend.api.reward_routes import reward_router
from backend.api.routes import router
from backend.api.telegram_routes import telegram_router
from backend.api.vlm_monitoring_routes import vlm_monitoring_router
from backend.api.voice_routes import voice_router
from backend.config import get_settings
from backend.db.base import SessionLocal
from backend.services.drug_image_recognition import _single_token_strength_index
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

    # B-08 production enablement (2026-08-28): get_drug_image_recognizer()
    # co @lru_cache(maxsize=1) - lan goi dau tien tai model OpenCLIP tu dia
    # (do that o local: request dau tien qua timeout, request thu 2 tro di
    # ~0.3s vi da cache). Neu khong warm o day, NGUOI DUNG THAT dau tien sau
    # moi lan container khoi dong lai se nhan RECOGNITION_TIMEOUT thay vi ket
    # qua nhan dien - warm truoc luc khoi dong de khong ai la nguoi "boc tham"
    # phai chiu do tre nay.
    if settings.drug_image_chat_recognition_enabled:
        warmup_started_at = time.monotonic()
        get_drug_image_recognizer()
        print(f"[INFO] Drug image recognition warmup complete: duration_ms={(time.monotonic() - warmup_started_at) * 1000:.2f}")
        # PR #160 review: _single_token_strength_index (catalog-derived OCR
        # single-token uniqueness check) is a module-level, process-lifetime
        # cache -- same convention as get_drug_image_recognizer() just
        # above, so the same reasoning applies: warm it here rather than
        # paying it inline on whichever real request first hits a
        # single-token OCR name match. Real local cost: 219ms for the
        # current ~3556-row catalog (measured directly, not estimated) --
        # small next to the OpenCLIP/OCR warmup above, but free to remove
        # from the request-latency path entirely at essentially no
        # additional startup cost. This process runs a single uvicorn
        # worker (Dockerfile CMD has no --workers flag) so there is only
        # ever one such cache to warm; if that ever changes to multiple
        # workers, this same startup hook already warms each worker's own
        # copy independently, exactly like the two warmups above it.
        single_token_index_started_at = time.monotonic()
        with SessionLocal() as warmup_session:
            single_token_index_size = len(_single_token_strength_index(warmup_session))
        print(
            "[INFO] OCR single-token uniqueness index warmup complete: "
            f"keys={single_token_index_size} duration_ms={(time.monotonic() - single_token_index_started_at) * 1000:.2f}"
        )

    # Vong 2, muc 13 (chatbot-rag-design.md) - scheduler nhac lai escalation.
    # SQLAlchemyJobStore (khong in-memory) - xem docstring escalation_scheduler.py.
    start_escalation_scheduler()
    print("[INFO] Escalation reminder scheduler started.")

    yield

    stop_escalation_scheduler()
    print("Shutting down...")


settings = get_settings()

# BUILD-18B P1 (Agent Architecture V2 BUILD-18 report, observability follow-
# up): nothing in this app ever configured Python's own `logging` module, so
# every `logging.getLogger(...).info(...)` call -- including
# backend/agents/v2/observability.py::StructuredLogSink, BUILD-13's own
# structured Agent V2 event sink -- was silently dropped everywhere (local
# dev and Railway alike), not just "not captured by Railway": logging's own
# handler-of-last-resort only emits WARNING and above. `settings.log_level`
# already existed as a config field but was never read anywhere until this
# line. This wires existing app loggers to stdout; it changes no event
# content, no allowlist, and no redaction rule (BUILD-13 is not redesigned).
logging.basicConfig(level=settings.log_level, format="%(message)s", stream=sys.stdout)

# BUILD-20 hardening: the line above is an intentional, necessary fix
# (BUILD-18B) -- but it also unmuzzles every *third-party* logger that had no
# explicit level of its own, since Python's root-logger level now applies to
# all of them too. httpx (used by the OpenAI SDK and by Vinmec Web fetches)
# logs one INFO line per outbound request containing the full request URL --
# for a GET request that is query-string-and-all, and Vinmec Web's search
# query is exactly the patient's own message, sanitized into a URL parameter.
# Confirmed live on staging during this build: "HTTP Request: GET
# https://www.vinmec.com/vie/tim-kiem/?q=<patient's own message text>" was
# appearing verbatim in the log stream -- BUILD-13/18B's own redaction
# allowlist (_sanitize_attributes) only governs this app's OWN
# telemetry.emit() calls; it was never able to see or filter a third-party
# library's own independent logging call. Raising httpx/httpcore's own
# logger level (not the root level, and not backend.agents.v2.telemetry's
# level) removes the one-line request/response summaries; it changes no
# event this app itself emits and no redaction rule BUILD-13 defined.
for _noisy_logger in ("httpx", "httpcore"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)
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
app.include_router(audit_router, prefix="/api/v1")
app.include_router(my_audit_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(agent_v2_router, prefix="/api/v1")
app.include_router(doctor_review_router, prefix="/api/v1")
app.include_router(patient_handoff_router, prefix="/api/v1")
app.include_router(agent_feedback_router, prefix="/api/v1")
app.include_router(admin_feedback_router, prefix="/api/v1")
app.include_router(admin_safety_router, prefix="/api/v1")
app.include_router(admin_monitoring_router, prefix="/api/v1")
app.include_router(escalation_router, prefix="/api/v1")
app.include_router(drug_router, prefix="/api/v1")
app.include_router(drug_image_router, prefix="/api/v1")
app.include_router(drug_image_chat_router, prefix="/api/v1")
app.include_router(patient_router, prefix="/api/v1")
app.include_router(prescription_router, prefix="/api/v1")
app.include_router(photo_router, prefix="/api/v1")
app.include_router(dose_router, prefix="/api/v1")
app.include_router(reporting_router, prefix="/api/v1")
app.include_router(caregiver_router, prefix="/api/v1")
app.include_router(rag_monitoring_router, prefix="/api/v1")
app.include_router(vlm_monitoring_router, prefix="/api/v1")
app.include_router(nudge_router, prefix="/api/v1")
app.include_router(health_log_router, prefix="/api/v1")
app.include_router(reward_router, prefix="/api/v1")
app.include_router(push_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(telegram_router, prefix="/api/v1")
app.include_router(notification_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


# Trigger hot reload for new router additions (reset-password-sync, verify-email-sync)
