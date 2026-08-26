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

# Cung sentinel-pattern nhu tren, ap dung cho JWT_SECRET (TASK-010,
# api-contracts.md muc 1) - gia tri nay CONG KHAI trong source nen KHONG
# duoc dung de ky JWT that, validator ben duoi raise ngay neu con giu nguyen.
_UNSET_JWT_SECRET_SENTINEL = "unset-jwt-secret-CHANGE-ME-for-any-shared-env"


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

    # Agent V2 model gateway.  Each workload may use a distinct OpenAI project
    # in production.  When a workload key is empty, the gateway may use the
    # existing OPENAI_API_KEY only for local/development compatibility; it
    # never exposes either credential to callers, prompts, or logs.
    openai_router_api_key: str = ""
    openai_main_api_key: str = ""
    openai_fallback_api_key: str = ""
    openai_embedding_api_key: str = ""
    openai_judge_api_key: str = ""
    agent_router_model: str = "gpt-5.4-nano"
    agent_main_model: str = "gpt-5.4-mini"
    agent_fallback_model: str = "gpt-5.4"
    agent_embedding_model: str = "text-embedding-3-small"
    rag_judge_model: str = "gpt-4o"
    # BUILD-13: JSON price catalog by exact model name. Prices are deliberately
    # not hard-coded because provider pricing/version contracts can change.
    # Example: {"gpt-5.4-mini":{"input_per_million":0.0,"cached_input_per_million":0.0,"output_per_million":0.0}}
    agent_model_pricing_json: str = "{}"
    # BUILD-32: a human-assigned label for whatever `agent_model_pricing_json`
    # currently holds, so a durably-persisted cost figure can always be traced
    # back to the price list that produced it (see AgentRun.pricing_version).
    # Bump this whenever the JSON above is edited; it is not derived/parsed
    # from the JSON itself.
    agent_model_pricing_version: str = "unversioned"

    # BUILD-33: production LLM Judge V2 (backend/agents/v2/judge_provider.py,
    # judge_rubrics.py, judge_eligibility.py, judge_input.py, backend/services/
    # agent_judge_worker.py). Distinct from `rag_judge_model`/
    # `openai_judge_api_key` above (BUILD-15's offline-only DeepEval judge,
    # `backend/agents/v2/deepeval_judge.py`, which by its own docstring is
    # "never imported by Agent runtime/Safety code" and only ever scores
    # versioned public golden RAG cases) -- this Judge scores REAL sampled/
    # ticketed production Agent V2 turns, so it gets its own settings/
    # provenance rather than silently reusing that module's model config,
    # even though the OpenAI *credential* below IS deliberately shared (same
    # provider, same "Judge" purpose, `openai_judge_api_key` already exists
    # for exactly this -- see judge_provider.py's credential resolver).
    #
    # Default OFF -- an operator must explicitly opt in once a real judge
    # credential is configured, same pattern as `agent_runtime_enabled`.
    agent_judge_enabled: bool = False
    # Project's stated target (BUILD-32-TO-36-MASTER-PLAN.md, BUILD-33 §2):
    # Gemini 3.7 Flash, thinking/reasoning=high. Verified real and reachable
    # 2026-08-25 (model ID `gemini-3.7-flash`, generally available; Google's
    # OpenAI-compatible endpoint `https://generativelanguage.googleapis.com/
    # v1beta/openai/` supports it with `reasoning_effort` mapped to its
    # `thinkingLevel` -- see BUILD-33 report §2). No new SDK dependency: the
    # existing `openai` package talks to it via `base_url` alone, the exact
    # precedent already proven in this repo by
    # backend/vlm_demthuoc/providers.py's own "gemini"/"aistudio"/"google"
    # base_url presets for a completely different (VLM) pipeline. Shipped as
    # the DEFAULT below per that stated target; there is no real
    # `GOOGLE_API_KEY` configured in this local dev environment, so a live
    # Gemini call could not be verified end-to-end this build (see report
    # §2/§13) -- `agent_judge_google_api_key` empty is a real, honest
    # `JUDGE_FAILED`/credential-not-configured state, never a silent
    # fallback to a different model.
    agent_judge_provider: Literal["openai", "google"] = "google"
    agent_judge_model: str = "gemini-3.7-flash"
    agent_judge_google_api_key: str = ""
    # Only sent when agent_judge_provider="google" (see judge_provider.py) --
    # an OpenAI model does not accept this parameter the same way.
    agent_judge_reasoning_effort: Literal["low", "medium", "high"] = "high"
    # Empty = provider default endpoint (OpenAI's own, or Google's OpenAI-
    # compat endpoint when provider="google" -- resolved in judge_provider.py,
    # never guessed from a bare provider-name abbreviation the way the
    # standalone VLM tool's own resolve_base_url() does, since this setting
    # is already an explicit enum).
    agent_judge_base_url: str = ""
    agent_judge_timeout_seconds: float = Field(default=30.0, gt=0, le=120.0)
    # No SDK-level retries (mirrors deepeval_judge.py's own TrackingGPT4oJudge
    # and vlm_demthuoc's OpenAICompatBackend reasoning): an exhausted Judge
    # provider failure must surface as JUDGE_FAILED, not silently retry and
    # inflate the background worker tick.
    #
    # Fraction of otherwise-non-eligible COMPLETED runs additionally sampled
    # for Judge review (on top of, never instead of, ticket/anomaly
    # eligibility -- see judge_eligibility.py). [CHUA CHOT] placeholder,
    # same caveat as this project's other not-yet-product-decided rate
    # constants (rate_limit_*, drug_confirmation_ttl_minutes above).
    agent_judge_sampling_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    # A heuristic (never model-authoritative) faithfulness/relevance score
    # below this threshold makes an otherwise-ordinary RAG/general-model run
    # LOW_SCORE-eligible for Judge review -- see judge_eligibility.py.
    agent_judge_low_score_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    # Bounds one scheduler tick's real LLM-call work (see
    # backend/services/agent_judge_worker.py::process_pending_judge_batch) --
    # a slow/degraded Judge provider must not let one tick run indefinitely.
    agent_judge_max_per_tick: int = Field(default=5, ge=1, le=50)
    agent_judge_poll_interval_seconds: float = Field(default=30.0, gt=0, le=3600.0)
    # Bump whenever the rubric prompts in judge_rubrics.py change meaning --
    # combined with agent_judge_model + rubric_version, this is the
    # duplicate-protection key (AgentRunJudge's own unique index) and the
    # provenance every persisted score can be traced back to.
    agent_judge_prompt_version: str = "judge-v1"
    agent_judge_rubric_version: str = "rubric-v1"

    # Database — PostgreSQL + pgvector (ADR-0008), KHONG dung vector DB rieng.
    database_url: str = "postgresql://vmec:vmec@localhost:5432/vmec04"

    # Pool SQLAlchemy — truoc day dung mac dinh ngam cua thu vien (pool_size=5,
    # max_overflow=10, pool_timeout=30s) vi create_engine() khong truyen tham
    # so nao. Demo that (nhieu nguoi cung dang nhap 1 tai khoan, cac trang poll
    # nhieu endpoint lien tuc) xac nhan qua log production: "sqlalchemy.exc.
    # TimeoutError: QueuePool limit of size 5 overflow 10 reached" -> 500 hang
    # loat, ung dung "treo". Chi chay 1 uvicorn worker (xem Dockerfile, khong
    # co --workers) nen toan bo traffic dung chung DUY NHAT pool nay - khong
    # phai chia nho cho nhieu process. Postgres production xac nhan max_connections=100,
    # dang dung ~14 luc kiem tra -> con du du dia de nang len.
    db_pool_size: int = Field(default=20, ge=1)
    db_max_overflow: int = Field(default=30, ge=0)
    db_pool_timeout: float = Field(default=15.0, gt=0, description="Giay cho truoc khi bao loi thay vi 30s mac dinh - fail nhanh hon de FE bao loi ro thay vi treo lau")

    # VLM dem thuoc (backend/services/photo_verification/vlm_bridge.py) — DUNG
    # CHUNG bien VLM_* voi backend/vlm_demthuoc/ (cong cu CLI doc lap), khong
    # phai vo tinh trung ten: ca hai cung goi mot endpoint dem thuoc, nen dung
    # chung mot bo cau hinh la dung, khong phai 2 nguon can dong bo.
    #
    # KHONG doc qua backend/vlm_demthuoc/config.py (os.environ + api_key.json
    # + getpass) - ham do danh cho CLI chay duoi may nguoi dung, khong hop
    # voi server (khong the "hoi nguoi dung" luc dang chay). pydantic-settings
    # o day la nguon duy nhat cho ca web server.
    vlm_api_key: str = ""
    vlm_provider: Literal["openai", "claude"] = "openai"
    vlm_base_url: str = ""
    vlm_model: str = ""
    vlm_json_mode: Literal["schema", "object", "off"] = "schema"
    # SDK openai mac dinh tu thu lai 2 lan khi qua gio, am tham nhan gap 3.
    vlm_timeout: float = Field(default=45.0, gt=0)
    # Endpoint lanh manh khong bao gio cham toi co che nay.
    vlm_retries: int = Field(default=5, ge=1)
    # Doi giua 2 lan thu. Test cua vlm_bridge.py dat 0 de khong ngu that giay
    # nao trong luc chay test (xem tests/services/photo_verification/test_vlm_bridge.py).
    vlm_retry_delay: float = Field(default=1.5, ge=0)

    # Langfuse Observability RIENG cho pipeline VLM (dem thuoc + doi chieu
    # don, backend/services/vlm_telemetry.py) - THEM 2026-08-22. Co Y tach
    # bien voi langfuse_*/LANGFUSE_* o duoi (dung cho RAG chatbot, khac
    # project/key that): 2 pipeline khac nhau hoan toan (mo hinh khac, nguoi
    # phu trach khac), dung chung 1 project se lam lan trace cua nhau. Rong
    # (mac dinh) = tat tracing, giong nguyen tac voi VAPID/langfuse_* o tren -
    # thieu khong phai loi hong, chi la mat 1 kenh quan sat phu.
    vlm_langfuse_public_key: str = Field(default="", description="Langfuse public key RIENG cho pipeline VLM")
    vlm_langfuse_secret_key: str = Field(default="", description="Langfuse secret key RIENG cho pipeline VLM")
    vlm_langfuse_host: str = Field(default="https://cloud.langfuse.com", description="Langfuse host cho VLM")
    vlm_langfuse_enabled: bool = Field(default=True, description="Bat/tat active tracing cho VLM")

    # Anh xac nhan lieu thuoc la du lieu y te (BR-4.3) - luu ngoai repo, DB chi
    # giu duong dan (backend/db/models.py::PhotoVerification.image_path).
    # Can gan Railway Volume vao mount path chua thu muc nay thi anh moi song
    # qua lan deploy lai (xem docs/DEPLOY.md muc "Volume anh xac nhan lieu").
    photo_storage_dir: str = "./data/photo_verifications"
    # B-03 catalog reference images are non-PHI and intentionally isolated
    # from uploaded dose-verification photos, while reusing local-volume
    # storage conventions until a reviewed storage backend is introduced.
    drug_image_storage_dir: str = "./data/drug_images"
    # Canh dai nhat sau khi resize + chat luong nen JPEG - dong bo voi
    # max_edge=1600, jpeg_quality=90 da tune tren golden dataset trong
    # backend/vlm_demthuoc/vlm_client.py::encode_frame, khong bia so moi.
    photo_max_edge_px: int = Field(default=1600, gt=0)
    photo_jpeg_quality: int = Field(default=90, ge=1, le=95)
    # So ngay giu FILE anh truoc khi backend/services/photo_cleanup.py xoa
    # (dong DB van giu lai lam audit trail, chi image_path ve None). Chia
    # theo ket_qua vi muc do can bang chung khac nhau - xem photo_cleanup.py.
    # [CAN CHOT]: 3 gia tri duoi la de xuat mac dinh, chua phai quyet dinh
    # san pham cuoi cung.
    photo_retention_days_khop: int = Field(default=14, gt=0)
    photo_retention_days_lech: int = Field(default=90, gt=0)
    photo_retention_days_stuck: int = Field(default=3, gt=0)

    # Retrieval (specs/chatbot-rag-design.md muc 4) — DA CHOT bang so lieu that
    # Phase 7 (2026-08-08, eval/run_eval.py + eval/eval_report.json), khong con
    # la doan mo hinh nua. O gia tri cu (0.5/0.3), 15/15 cau out-of-domain
    # (thuoc khong ton tai, go sai nghiem trong, van ban khong lien quan) DEU
    # lot qua nguong (100% false-accept) - BR-7.3 "khong co nguon -> tu choi"
    # khong hoat dong. 0.60/0.55 giam false-accept tong the tu 100% -> ~47%
    # (con "thuoc khong ton tai" van kho o ~83%, xem chatbot-rag-design.md
    # muc 10 #12 - can them lop phong ve khac, khong chi tune nguong), doi lai
    # GT recall giam tu ~100% xuong 81.2% (26/32 cau) - xem muc 10 #1/#8 cho
    # chi tiet day du + bang trade-off cac muc khac da can nhac.
    rrf_k: int = 60
    retrieval_top_k: int = 5
    nguong_vector: float = Field(
        default=0.60, description="Chot 2026-08-08 tu eval/ Phase 7 - xem chatbot-rag-design.md muc 10 #1"
    )
    nguong_lexical: float = Field(
        default=0.55, description="Chot 2026-08-08 tu eval/ Phase 7 - xem chatbot-rag-design.md muc 10 #8"
    )
    # Chot 2026-08-09 (vong 2, muc 6/15 - phat hien qua review, KHONG phai gia
    # dinh mac dinh pgvector): mac dinh pgvector (40) chi dat HNSW recall vs
    # exact scan 84.4% tren 32 cau GT (~15% cau hoi that su bi HNSW bo sot
    # dung chunk gan nhat, khong lien quan gi toi nguong/RRF - loi o TANG TIM
    # UNG VIEN GOC). Sweep that {40,60,80,100,150,200}: 100 la diem dat 100%
    # recall vs exact scan (giu nguyen tu 100 den 200 - khong ich loi gi khi
    # tang them), doi lai ~3x latency truy van vector thuan (46ms->128ms trung
    # binh, do co kiem soat/xen ke thu tu tranh nhieu do cache) - chap nhan
    # duoc vi chi la 1 phan nho trong tong do tre 1 luot chat (3-4 lan goi LLM,
    # tung lan >=500ms, xem muc 2), va chi ap dung nhanh out-of-prescription
    # (muc 11.2), khong phai moi tin nhan. Xem chatbot-rag-design.md muc 15,
    # eval/hnsw_recall_tuning.py.
    hnsw_ef_search: int = Field(
        default=100, description="Chot 2026-08-09 tu eval/hnsw_recall_tuning.py - xem chatbot-rag-design.md muc 15"
    )
    drug_knowledge_backend: Literal["v1", "v2", "shadow"] = Field(
        default="v2",
        description="Controlled V2 default. Use v1 for rollback; shadow returns V1 while comparing V2.",
    )
    drug_knowledge_v2_dir: str | None = Field(
        default=None,
        description="Directory containing deployable Canonical V2 JSONL artifacts. Defaults to the local migration output.",
    )
    prescription_v2_mode: Literal["legacy", "shadow"] = Field(
        default="legacy",
        description="APP-3 server-side prescription mode. Shadow writes deterministic V2 sidecar rows atomically.",
    )
    dose_runtime_mode: Literal["legacy", "shadow", "v2"] = Field(
        default="legacy",
        description="APP-4 dose runtime mode. Shadow generates/reconciles V2 rows; v2 serves the legacy-compatible V2 adapter.",
    )
    safety_runtime_mode: Literal["legacy", "shadow"] = Field(
        default="legacy",
        description="APP-5 safety mode. Shadow persists audited V2 safety/outbox decisions; legacy disables this runtime path.",
    )
    # Agent V2 begins isolated and disabled. BUILD-1 has no write actions.
    agent_runtime_enabled: bool = False
    agent_token_budget: int = Field(default=4096, ge=1, le=100_000)
    # Fix for a production BUDGET_EXCEEDED report on "Ngay mai toi can uong
    # thuoc gi" (what do I take tomorrow): unlike get_today_doses (bounded to
    # exactly one calendar day), get_upcoming_doses had NO upper bound at all
    # -- ``scheduled_at >= now`` returns every future dose group through the
    # end of the patient's entire prescription. Reproduced locally (real
    # in-process orchestrator, real OpenAI usage) against an ordinary 60-day,
    # 2-drug chronic regimen: 179 upcoming groups, 100KB+ serialized into the
    # synthesis prompt, real usage 47,487 tokens against the 4,096 budget --
    # an 11x overrun from a routine prescription, not an edge case.
    #
    # default=1 (today's remainder + all of tomorrow, calendar-date bound so
    # it never clips "tomorrow" regardless of what time it is right now) was
    # chosen empirically, not guessed: real repro runs showed 2- and 3-day
    # windows still failed intermittently (the model non-deterministically
    # sometimes calls get_today_doses *and* get_upcoming_doses together,
    # e.g. 3 days -> 4,829 real tokens on one run, 4,001 on another, both
    # against the SAME 4,096 budget) -- too thin a margin to call fixed. 1
    # day landed at 2,448-2,557 real tokens across repeat runs, ~35-40%
    # headroom under budget even in that worst-case two-tool combination.
    # This tool's own declared description ("Read the authorized patient's
    # upcoming doses.") never promised the full remaining prescription, so
    # bounding this is a behavior-preserving fix for "tomorrow", not a
    # capability cut. A longer forward window (e.g. for "sap toi"/"this
    # week" phrasing) is a reasonable future improvement but needs either a
    # leaner evidence payload or a deliberate, separately-reviewed budget
    # change, not a guess bundled into this fix -- see report
    # 57-build-27-budget-exceeded-upcoming-doses.md. Token budget itself left
    # untouched by design (explicit instruction: do not raise it as this fix).
    agent_upcoming_doses_window_days: int = Field(default=1, ge=1, le=90)
    # BUILD-20: every tool-calling run now costs (1 planning step) + (1 step
    # per tool call) + (1 synthesis step) -- see runtime.py's
    # Planning -> Tools -> Synthesis loop (BUILD-19B). The pre-synthesis
    # default of 4 was sized for the old single-model-turn design and left no
    # room for synthesis at all once 3+ tools were called; BUILD-19B's live
    # staging UAT reproduced this concretely on the prescription-query flow
    # (get_active_prescriptions + get_today_doses + get_upcoming_doses =
    # 3 tool calls -> 1+3=4 already exhausted the old default before
    # synthesis could run, so it failed closed to BUDGET_EXCEEDED instead of
    # answering). 6 gives exactly enough headroom for up to 4 tool calls plus
    # planning and synthesis, and was the exact value verified live against
    # that scenario (see report 24-build-19b, "Staging configuration"). Not
    # widened further "just to pass" -- 4 tool calls covers every real
    # multi-tool flow observed in UAT so far with one call of margin.
    agent_max_steps: int = Field(default=6, ge=1, le=20)
    # BUILD-21: comma-separated account ids allowed to reach Agent V2 while
    # ``agent_runtime_enabled`` is true, ON TOP OF that flag (both must hold).
    # Empty (the default) means "no extra restriction" -- unchanged behavior
    # for every environment except production during its canary, so staging/
    # local UAT never needs this set. On production, this is the explicit,
    # auditable allowlist of test/internal accounts -- always granted access
    # regardless of ``agent_rollout_percentage`` below, since these accounts
    # are never meant to depend on a random bucket. An account neither on a
    # *non-empty* allowlist nor in the rollout percentage's bucket gets
    # exactly the same 404 as when the flag itself is off -- indistinguishable
    # from the outside, so a non-canary caller learns nothing about Agent
    # V2's existence.
    agent_canary_allowlist: str = ""
    # BUILD-23: deterministic percentage-of-traffic rollout, additive on top
    # of (never a replacement for) the allowlist above -- see
    # backend.api.agent_v2_routes._in_rollout_percentage. 0 (the default)
    # changes nothing: only allowlisted accounts get in, exactly like every
    # build through BUILD-22C. This is the mechanism the BUILD-23 cutover
    # plan's 5% -> 20% -> 50% -> 100% stages actually execute through; BUILD-23
    # itself never sets this above 0 on production (see report 29-build-23).
    agent_rollout_percentage: int = Field(default=0, ge=0, le=100)
    # BUILD-22: how long a client-supplied ``idempotency_key`` on
    # /agent/v2/orchestrate stays valid for replay (see
    # backend.services.agent_idempotency). Past this TTL the same key starts
    # a genuinely new run instead of replaying a stale cached result -- a
    # deliberately explicit, bounded replay window rather than "forever".
    agent_idempotency_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    agent_max_model_calls: int = Field(default=2, ge=1, le=10)
    agent_max_tool_calls: int = Field(default=6, ge=0, le=20)
    agent_max_retries: int = Field(default=1, ge=0, le=5)
    agent_model_timeout_seconds: float = Field(default=15.0, gt=0, le=120.0)
    agent_run_timeout_seconds: float = Field(default=30.0, gt=0, le=300.0)
    # BUILD-9: a late or unavailable Safety Domain result is terminal; this
    # limit is deliberately independent from model and run timeouts.
    agent_safety_timeout_seconds: float = Field(default=5.0, gt=0, le=30.0)
    # BUILD-4 context manager. The input budget is independently capped and
    # must leave the configured reserve available for a model response.
    agent_context_token_budget: int = Field(default=3072, ge=1, le=100_000)
    agent_output_token_reserve: int = Field(default=1024, ge=1, le=100_000)
    agent_context_short_term_fraction: float = Field(default=0.10, ge=0.0, le=1.0)
    agent_context_long_term_facts_fraction: float = Field(default=0.04, ge=0.0, le=1.0)
    agent_context_episodic_fraction: float = Field(default=0.03, ge=0.0, le=1.0)
    agent_context_semantic_fraction: float = Field(default=0.03, ge=0.0, le=1.0)
    # BUILD-7 retrieval gateway. These bounds apply before Retrieval Context
    # reaches the global Context Manager budget.
    agent_retrieval_top_k: int = Field(default=5, ge=1, le=20)
    agent_retrieval_token_budget: int = Field(default=700, ge=1, le=20_000)
    # BUILD-8: public supplementary knowledge only. This does not enable the
    # Agent runtime and must remain constrained to the explicit Vinmec hosts.
    agent_vinmec_web_enabled: bool = False
    agent_vinmec_web_max_calls: int = Field(default=1, ge=0, le=5)
    agent_vinmec_web_max_results: int = Field(default=3, ge=1, le=10)
    agent_vinmec_web_timeout_seconds: float = Field(default=5.0, gt=0, le=30.0)
    agent_vinmec_web_token_budget: int = Field(default=600, ge=1, le=10_000)
    # Vong 4, muc 3.2 - chi dung cho fuzzy name search o nhanh thuoc NGOAI
    # don. Sweep 4 tap eval (full/short GT, OOD, ambiguous) ban dau chot 0.25,
    # nhung 0.25 chi co margin +0.012 tren tran OOD (0.238) - sweep MIN them
    # 0.25-0.30 (buoc 0.01, phan hoi review 2026-08-14) xac nhan GT-short van
    # 100% toi 0.28, tut xuong 90% (case "fluopas") tu 0.29 - chot 0.28 (diem
    # cuoi TRUOC khi tut), margin tang len +0.042, khong danh doi gi (GT-full/
    # GT-short/OOD/ambiguous deu giu nguyen so voi 0.25). Rieng OOD: bo sung
    # 10 brand NGAN khong ton tai (eval/short_ood_nonexistent.json, 15 cau OOD
    # cu deu la cau hoi day du, khong dai dien dung use-case ngan cua muc nay)
    # - phat hien "feverex" (0.208, gap=0.093) se lot fast-path SAI o
    # nguong_cao 0.15/0.20 (cu), cung co them ly do chon 0.28 thay vi so thap
    # hon. gap la tuyen phong thu chinh de case nhieu SKU khong lot fast-path.
    fuzzy_name_high_threshold: float = Field(
        default=0.28, ge=0.0, le=1.0, description="Vong 4: top-1 fuzzy score toi thieu de bo qua LLM review"
    )
    fuzzy_name_gap_threshold: float = Field(
        default=0.05, ge=0.0, le=1.0, description="Vong 4: cach biet top-1/top-2 toi thieu de bo qua LLM review"
    )
    # Vong 4, muc 4: cosine chi loc rong candidate tac_dung_phu cua thuoc
    # active truoc LLM nhị phan. Sweep 11 case co nhan: 0.20 giu 12/12
    # match dung (recall 100%); false positive con lai duoc LLM loai, khong
    # bao gio ghi audit tu cosine don thuan.
    side_effect_candidate_threshold: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Vong 4: cosine toi thieu de dua chunk tac_dung_phu active vao LLM audit matcher",
    )

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

    # auth-api that (TASK-010, api-contracts.md muc 1) - ky/giai ma JWT
    # (Authorization: Bearer <JWT>, payload sub+role). Fail-closed giong het
    # internal_auth_secret o tren, cung 1 ly do: JWT_SECRET la nen tang bao
    # mat toan bo he thong, khong duoc phep am tham chay voi gia tri sentinel.
    jwt_secret: str = Field(
        default=_UNSET_JWT_SECRET_SENTINEL,
        description="TEMP sentinel - PHAI dat that qua env truoc khi chay (TASK-010)",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, description="Khop expires_in=3600 trong api-contracts.md muc 1")
    refresh_token_expire_days: int = 30

    # Supabase Auth (ADR-0013)
    supabase_url: str = Field(default="", description="Supabase Project URL")
    supabase_anon_key: str = Field(default="", description="Supabase Anon/Public Key")
    supabase_service_role_key: str = Field(default="", description="Supabase Service Role Key (Server only)")

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_must_be_configured(cls, v: str) -> str:
        if not v or v == _UNSET_JWT_SECRET_SENTINEL:
            raise ValueError(
                "JWT_SECRET chua duoc cau hinh that (con rong hoac la sentinel cong khai "
                f"{_UNSET_JWT_SECRET_SENTINEL!r} - gia tri nay NAM SAN TRONG SOURCE nen KHONG duoc "
                "dung de chay that). Dat JWT_SECRET trong .env (khong commit gia tri that) truoc khi "
                "khoi dong app hoac chay test - xem TASK-010."
            )
        return v

    # Web Push (VAPID) - nhac gio uong thuoc toi duoc benh nhan ngay CA KHI
    # da dong han tab/trinh duyet, thu ma co che poll o client khong lam duoc
    # (xem backend/services/dose_push_reminder.py). Sinh 1 lan bang `vapid --gen`
    # hoac py_vapid - la chuan mo, KHONG can dang ky dich vu ben thu 3 nao.
    #
    # CO Y de default RONG va KHONG fail-closed, khac han internal_auth_secret/
    # jwt_secret o tren: thieu 2 secret kia la LO HONG BAO MAT (phai chan app
    # khoi dong), con thieu VAPID chi la KHONG CO TINH NANG push - app van
    # chay dung, nhac o client van hoat dong. Bat buoc cau hinh se lam vo moi
    # truong local cua ca nhom chi vi 1 tinh nang phu.
    vapid_public_key: str = Field(default="", description="Khoa cong khai VAPID (base64url). Rong = tat push.")
    vapid_private_key: str = Field(default="", description="Khoa rieng VAPID (base64url) - KHONG commit.")
    vapid_subject: str = Field(
        default="mailto:capymedi@example.com",
        description="Lien he chu so huu theo chuan VAPID - mailto: hoac https:",
    )

    # Rate limiter (vong 2, chatbot-rag-design.md muc 12.4) - theo patient_id,
    # KHONG theo IP (nhieu benh nhan co the chung mang nha/benh vien). [CAN
    # CHOT - thuc nghiem] 2 gia tri duoi la PLACEHOLDER dua tren co so chi phi
    # da do Phase 3/7 (1 luot chat = 3-4 lan goi LLM, gpt-4o-mini re) - CHUA
    # phai so cuoi cung, can Architect xac nhan lai khi co du lieu su dung
    # that (xem src/api/rate_limit.py).
    rate_limit_max_requests: int = Field(
        default=20, description="[CAN CHOT] so request toi da/patient_id trong 1 window"
    )
    rate_limit_window_seconds: float = Field(default=60.0, description="Do dai window rate limit (giay)")

    # BUILD-29: separate, tighter limiter for POST /agent/v2/feedback (a
    # patient reporting a bad reply) -- reuses the same SlidingWindowRateLimiter
    # class as the chat rate limiter above (backend/api/rate_limit.py) but its
    # own instance/threshold, since "how many chat messages/minute" and "how
    # many issue reports/minute" are unrelated usage patterns that should not
    # share one budget. [CHUA CHOT] placeholder values, same caveat as the
    # chat rate limiter above -- generous enough that a genuine double-click
    # or a handful of real reports in one session never gets falsely limited.
    agent_feedback_rate_limit_max_requests: int = Field(
        default=10, description="[CHUA CHOT] so feedback report toi da/actor trong 1 window"
    )
    agent_feedback_rate_limit_window_seconds: float = Field(
        default=300.0, description="Do dai window rate limit cho feedback report (giay)"
    )

    # TTL cho pending_drug_confirmation (vong 2, chatbot-rag-design.md muc
    # 11.3) - THEM 2026-08-09, phat hien qua review: benh nhan bo do 1 cau
    # hoi giua chung (khong tra loi xac nhan) se de lai pending state TREO
    # VINH VIEN neu khong co TTL - tin nhan KHONG lien quan gui sau do (ke ca
    # vai ngay sau) se bi hieu NHAM la dang tra loi cau hoi xac nhan cu.
    # [CAN CHOT - thuc nghiem] 30 phut la PLACEHOLDER hop ly cho 1 phien chat
    # dang hoi thoai (du dai cho tra loi tu nhien, du ngan de tranh nham lan
    # thuc te) - CHUA phai so cuoi, can Architect xac nhan lai. Kiem tra o
    # get_pending_confirmation() (check-on-read, khong can APScheduler/job
    # rieng - xem ghi chu trong drug_confirmation_store.py).
    drug_confirmation_ttl_minutes: float = Field(
        default=30.0, description="[CAN CHOT] TTL cho 1 pending_drug_confirmation truoc khi bi coi la het han"
    )

    # Escalation reminder scheduler (vong 2, chatbot-rag-design.md muc 13) -
    # tan suat quet cac escalation OPEN de kiem tra co den moc nhac lai chua
    # (t=15p/25p/35p, xem src/services/escalation_reminder.py). [CAN CHOT -
    # thuc nghiem] 60 giay la PLACEHOLDER hop ly (moc nhac gan nhat cach nhau
    # 10 phut, quet moi 60s du chi tiet, khong tai DB qua muc can thiet) -
    # CHUA phai so cuoi, can Architect xac nhan lai.
    escalation_reminder_check_interval_seconds: float = Field(
        default=60.0, description="[CAN CHOT] tan suat quet escalation can nhac lai (giay)"
    )

    # Langfuse Observability & Monitoring (docs/langfuse_rag_admin_monitoring_spec.md)
    langfuse_public_key: str = Field(default="", description="Langfuse public key (pk-lf-...)")
    langfuse_secret_key: str = Field(default="", description="Langfuse secret key (sk-lf-...)")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", description="Langfuse API host URL")
    langfuse_enabled: bool = Field(default=True, description="Enable or disable active Langfuse tracing")
    rag_prompt_version: str = Field(default="medication-chat-v1.0", description="RAG answer prompt version")
    rag_retriever_version: str = Field(default="hybrid-rrf-v2", description="Retriever pipeline version")
    rag_index_version: str = Field(default="med-kb-2026-08-20", description="Knowledge base index version")



@lru_cache
def get_settings() -> Settings:
    return Settings()
