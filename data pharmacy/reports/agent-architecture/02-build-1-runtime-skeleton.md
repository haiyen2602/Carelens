# BUILD-1 — Agent Boundary + Runtime Skeleton

Date: 2026-08-18  
Scope: isolated, OFF-by-default, read-only Agent V2 foundation. No Agent write action, Doctor Handoff, Vinmec web search, long-term memory, RAG redesign, Agent persistence migration, Railway work, or change to the legacy chat route was made.

## Implementation

### Isolated path and safe default

- Added `POST /api/v1/agent/v2/read-only` in `backend/api/agent_v2_routes.py`.
- Added `AGENT_RUNTIME_ENABLED` (default `false`), `AGENT_MAX_STEPS` (default `2`), and `AGENT_MAX_TOOL_CALLS` (default `6`) through `backend/config.py`.
- The endpoint returns 404 while the flag is OFF, before authorizing or querying a patient. `POST /api/v1/chat` remains unchanged and is still the legacy compatibility path.
- The BUILD-1 route has no input that can represent a write action.

### Authorization — P0 boundary

`backend/agents/v2/authorization.py::require_agent_patient_access` derives access server-side and fails closed before the Tool Gateway is constructed:

| Actor | Allowed patient context |
| --- | --- |
| Patient | Exact `patient_id` from the JWT only |
| Caregiver | Matching `CaregiverLink` with `accepted` status |
| Doctor | Matching approved `DoctorWatch` relationship |
| Admin / unknown / missing relationship | Denied |

This deliberately does not reuse legacy chat's permissive body-ID behavior for doctor/caregiver callers.

### Runtime, model, and tools

- `backend/agents/v2/runtime.py` defines a bounded read-only run with explicit terminal states: `COMPLETED`, `BUDGET_EXCEEDED`, `TOOL_DENIED`, and `FAILED`.
- `backend/agents/v2/model_gateway.py` defines a provider-neutral `ModelGateway` protocol plus `DisabledModelGateway` and `StaticModelGateway` test double. BUILD-1 makes no external model request.
- `backend/agents/v2/tools.py` has an explicit read-only allowlist:

```text
search_drug
get_drug_info
get_active_prescriptions
get_today_doses
get_upcoming_doses
get_dose_status
```

- Tools are adapters around Final Canonical Drug V2 and existing prescription/dose domain services. The new runtime does not import legacy LangGraph node modules or directly access ORM tables itself.
- Any unapproved tool name is denied; an over-budget plan is stopped before executing a tool.

## Validation

### Passed locally

```text
pytest -q --noconftest tests/test_agent_v2_runtime.py tests/test_agent_v2_route.py
6 passed

ruff check backend/agents/v2 backend/api/agent_v2_routes.py tests/test_agent_v2_runtime.py tests/test_agent_v2_route.py
PASS

python -m compileall -q backend/agents/v2 backend/api/agent_v2_routes.py backend/config.py backend/models/schemas.py backend/main.py
PASS

git diff --check
PASS
```

The unit cases prove patient self-binding, caregiver/doctor relationship denial and approval, tool allowlisting, tool-budget enforcement, terminal statuses, and the OFF-by-default endpoint gate.

### BUILD-1B validation closeout — BLOCKED

BUILD-1B rechecked local infrastructure on 2026-08-18. Docker Desktop's Linux engine is still unavailable, so no local PostgreSQL service can be created. Consequently, `alembic upgrade head`, Agent V2 API/integration authorization tests, all six real read-only-tool checks against seeded data, and legacy chat regression cannot run.

```text
docker compose up -d db
failed: dockerDesktopLinuxEngine is not running
```

The prior focused API/legacy command reached its PostgreSQL dependency and failed only with connection refusal. `Pillow` was installed to resolve the earlier test-collection dependency; the remaining blocker is infrastructure, not a test assertion. No unavailable validation is presented as a pass.

## Remaining gates before BUILD-2

1. Start Docker Desktop (or provide a clean reachable PostgreSQL), run `alembic upgrade head`, then run the focused Agent V2 API authorization tests and legacy chat regressions.
2. Exercise each typed read tool against seeded Canonical Drug V2, prescription, and V2 dose data on PostgreSQL.
3. Keep `AGENT_RUNTIME_ENABLED=false` until those gates pass. BUILD-2 must add real model smoke tests through the Model Gateway; it must not enable writes.

## Conclusion

BUILD-1: BLOCKED

DATABASE: FAIL — Docker daemon/engine unavailable; PostgreSQL cannot start and Alembic cannot be run.

AUTHORIZATION INTEGRATION: FAIL — unit authorization passed, but the JWT/API/real-relationship integration gate cannot run without PostgreSQL.

READ-ONLY TOOLS: FAIL — allowlist/unit behavior passed, but the six required real seeded-data tool calls cannot run without PostgreSQL.

AUTHORIZATION: PASS — unit-tested fail-closed Agent V2 actor/patient boundary; PostgreSQL integration validation remains pending.

RUNTIME: PASS — isolated OFF-by-default read-only skeleton, bounded execution, terminal states, and deterministic model test double are implemented.

TOOLS: PASS — explicit six-tool read-only allowlist is implemented; real PostgreSQL domain-tool validation is pending.

LEGACY REGRESSION: FAIL — not runnable in this environment because PostgreSQL/Docker is unavailable; legacy code was not modified.

READY FOR BUILD-2: NO

## Superseding BUILD-1C final status

BUILD-1: PASS

DATABASE: PASS

AUTHORIZATION INTEGRATION: PASS

READ-ONLY TOOLS: PASS

LEGACY REGRESSION: PASS

READY FOR BUILD-2: YES

## BUILD-1C infrastructure validation — PASS

Docker Desktop was available for the retry. PostgreSQL Compose service was healthy on local port 5432.

```text
alembic upgrade head
alembic current
0029 (head)
```

Final Canonical Drug V2 was imported against this database. The first run created `3556` products, `3556` ID maps, `1406` ingredients, and `5287` valid product-ingredient links; the second run created zero rows and artifact hashes remained unchanged.

Agent V2 authorization integration ran through `POST /api/v1/agent/v2/read-only` with the flag enabled only inside the validation process, then reset to false. Patient self-access passed; caregiver and doctor requests were denied without an accepted `CaregiverLink`/`DoctorWatch`, and passed after the matching relationship was seeded.

All six read-only tools were exercised against the imported canonical catalog plus a transaction-scoped prescription/item/occurrence fixture that was rolled back after validation:

```text
search_drug: PASS
get_drug_info: PASS
get_active_prescriptions: PASS
get_today_doses: PASS
get_upcoming_doses: PASS
get_dose_status: PASS
```

Focused regression result:

```text
pytest -q tests/test_agent_v2_runtime.py tests/test_agent_v2_route.py tests/test_chat_security_gate.py tests/test_chat_routes.py
16 passed
```

`AGENT_RUNTIME_ENABLED` remains false by default and was not enabled for normal runtime traffic.

## BUILD-1C required status

BUILD-1: PASS

DATABASE: PASS

AUTHORIZATION INTEGRATION: PASS

READ-ONLY TOOLS: PASS

LEGACY REGRESSION: PASS

READY FOR BUILD-2: YES

## BUILD-1B required status

BUILD-1: BLOCKED

DATABASE: FAIL

AUTHORIZATION INTEGRATION: FAIL

READ-ONLY TOOLS: FAIL

LEGACY REGRESSION: FAIL

READY FOR BUILD-2: NO

## Superseding BUILD-1C final status

BUILD-1: PASS

DATABASE: PASS

AUTHORIZATION INTEGRATION: PASS

READ-ONLY TOOLS: PASS

LEGACY REGRESSION: PASS

READY FOR BUILD-2: YES
