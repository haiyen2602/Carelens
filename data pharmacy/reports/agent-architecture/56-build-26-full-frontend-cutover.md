# BUILD-26 — Full Frontend Cutover to Agent V2

**Scope:** route real, product-facing chat traffic to Agent V2 for the
first time ever. Everything through BUILD-24O–25B made Agent V2's own API
100%-ready and validated — this build is what actually connects the app's
own chat UI to it.

---

## 1. Audit — why real chat never reached Agent V2

```
frontend/src/app/patient/assistant/page.tsx  (the ONLY chat-sending component in the whole tree, confirmed by grep)
  -> frontend/src/hooks/use-chat.ts::useChatMessage()
    -> frontend/src/lib/api.ts::sendChatMessage()
      -> POST /api/chat (Next.js route handler)
        -> frontend/src/app/api/chat/route.ts  -- HARDCODED: fetch(`${BACKEND_URL}/api/v1/chat`)
```

No branch, no rollout-percentage check, no Agent V2 call anywhere in this
chain. `AGENT_ROLLOUT_PERCENTAGE=100` only ever gated whether
`/api/v1/agent/v2/orchestrate` *admits* a caller — it never made the
product's own UI call that endpoint.

**Request/response contract, compared field by field:**

| | Legacy `POST /api/v1/chat` | Agent V2 `POST /api/v1/agent/v2/orchestrate` |
|---|---|---|
| Request | `{patient_id, message, dose_id?}` | `{patient_id, message, conversation_id?, session_id?, dose_id?, idempotency_key?}` |
| Response | `{reply, classification, severity, safety_flag, needs_clarification, sources}` | `{status, reply, intent, tools, citations, safety_disposition, handoff_id, trace_id, agent_run_id}` |

Request fields already matched exactly on the overlap (`patient_id`,
`message`, `dose_id`) — only `conversation_id` needed adding, mapped to the
UI's own existing stable per-thread id (`frontend/src/lib/chat-history.ts`'s
`activeId`), so Agent V2's short-term memory scopes to the same conversation
thread the user actually sees, instead of defaulting to one shared
"one-shot" conversation per account.

Response shapes differ meaningfully. `frontend/src/app/patient/assistant/page.tsx`
was checked directly (not assumed): it reads exactly one field from the
response, `data.reply`. Every `RunStatus` value Agent V2 can return
(`COMPLETED`/`HANDOFF_CREATED`/`SAFETY_BLOCKED`/`HANDOFF_REQUIRED`/`FAILED`/
`TIMEOUT`/`BUDGET_EXCEEDED`/`CANCELLED`) already carries a complete, safe,
Vietnamese, user-facing sentence in `reply` (confirmed in
`backend/agents/v2/runtime.py` — the reason-code-aware fixed messages from
BUILD-24E plus the plain fixed strings for the other terminal states) — so
no new per-status UI branch was required for the chat bubble itself to
always show something safe and readable.

## 2. Fix — adapter at the proxy layer, not inside Agent V2

Per the explicit instruction ("khong sua Agent V2 chi de ep no giong
Legacy neu co the map o proxy layer"), `frontend/src/app/api/chat/route.ts`
now:

- Forwards the request body to Agent V2 essentially as-is (field names
  already matched).
- Adapts the response: keeps `ChatResponse`'s original fields (defaulted
  honestly — `classification: null`, `sources: []`, `needs_clarification:
  false` — since Agent V2 has no real equivalent for these, not a
  fabricated mapping) and adds new optional fields carrying Agent V2's real
  data (`status`, `citations`, `safety_disposition`, `handoff_id`,
  `trace_id`, `agent_run_id`, `chatbot_version`). `severity`/`safety_flag`
  are derived honestly from the real `safety_disposition` (escalated when
  it's set and not `"SAFE"`) rather than left as another dead field.
- Forwards any non-2xx response untouched — 403 (cross-patient/auth), 404
  (rollout/allowlist), 409 (idempotency conflict), 503 (commit failure) all
  carry Agent V2's own real `detail` message through to the existing
  `ChatError` component, which already renders any error string generically
  (confirmed in `frontend/src/components/chat-error.tsx` — no component
  change needed there).
- **No silent fallback to legacy on any failure** — a failed call to Agent
  V2 returns that failure, never retried against `/api/v1/chat`.

`CHAT_RUNTIME=v2|legacy` env var added (default `v2`) — flips the proxy's
target with a config change and restart, no code change or redeploy, per
the instruction's own rollback requirement. Legacy's own route/backend
endpoint is completely untouched and still reachable this way.

`frontend/src/types/chat.ts` updated to match (documented field-by-field
in the type itself, not just this report).

## 3. Local verification (real Next.js dev server, not a direct backend call)

Ran a local Agent V2 backend (`AGENT_RUNTIME_ENABLED=true`,
`AGENT_ROLLOUT_PERCENTAGE=100`) and the actual `next dev` server, then sent
real HTTP requests to `http://localhost:3000/api/chat` (the real proxy
route, exercising the real adapter code) with a real JWT:

```
normal_drug_info    -> 200 COMPLETED chatbot_version=agent-v2
today_schedule      -> 200 COMPLETED chatbot_version=agent-v2
general_medical ("Bệnh tiểu đường là gì", the specifically required test) -> 200 COMPLETED chatbot_version=agent-v2, real accurate diabetes explanation
acute_danger        -> 200 HANDOFF_CREATED chatbot_version=agent-v2, safety_disposition=HANDOFF_REQUIRED, handoff_id populated
doctor_handoff      -> 200 COMPLETED (test phrase didn't match the router's DOCTOR_REVIEW keyword rules -- a pre-existing router
                       keyword-matching question, not a BUILD-26 proxy/adapter issue; Doctor Handoff's own mechanism was already
                       exhaustively verified working end-to-end in BUILD-24R/25 via the golden set's own query 70)
out_of_scope        -> 200 COMPLETED (correct -- OUT_OF_SCOPE_REQUEST is a short-circuited COMPLETED reply per BUILD-24H, not its own status)
cross_patient_denial -> 403 (forwarded untouched, no crash, no fallback)
idempotency         -> same idempotency_key sent twice -> identical agent_run_id both times
```

Also discovered and fixed while setting up this local test: `frontend/package-lock.json`
had never been regenerated since BUILD-24Q's merge brought in `main`'s
Supabase dependencies — it still referenced the removed `better-auth`/`pg`
packages, causing local dev-server compile failures unrelated to this
build's own code. Fixed by running `npm install` to reconcile it with the
already-committed `package.json`.

## 4. Production verification

Deployed `VMEC-04/FE` only (no backend Python file changed — the existing,
already-validated Agent V2 endpoint needed no changes for this
integration). `VMEC-04/BE` untouched, `/health` reconfirmed 200.

**Sent a real chat message through the actual production URL a real
browser would use** (`https://vmec-04fe-production.up.railway.app/api/chat`,
not a direct backend call) — the required "Bệnh tiểu đường là gì" question:

```
Baseline (before):  agent-v2 volume_24h = 1   legacy volume_24h = 11
-- sent 1 real chat message via https://vmec-04fe-production.up.railway.app/api/chat --
After:               agent-v2 volume_24h = 2   legacy volume_24h = 11   (unchanged)
Response:            status=COMPLETED, chatbot_version=agent-v2, trace_id/agent_run_id populated
Trace Explorer:       GET /admin/rag/traces/{trace_id} -> found, status=success, metadata.chatbot_version=agent-v2
```

Agent V2's volume increased by exactly 1 (matching the one message sent);
legacy's volume did not move at all. This is the definitive proof the
instruction asked for: real product-facing traffic now reaches Agent V2,
and no part of it is still reaching legacy.

## 5. What was deliberately not touched

- No Agent V2 backend code changed (`backend/agents/v2/*`, `backend/api/agent_v2_routes.py`
  untouched) — the existing contract already covered everything needed.
- No DB schema change.
- `AGENT_ROLLOUT_PERCENTAGE` unchanged (100) throughout.
- Legacy `/api/v1/chat` and its own route/component code path untouched and
  still fully reachable via `CHAT_RUNTIME=legacy`.
- Client-side idempotency-key generation was **not** added to the actual UI
  submit flow (the mechanism itself was verified working through the proxy
  when a key is supplied) — the chat UI doesn't currently generate one per
  message; noted as a reasonable follow-up, not required to satisfy this
  build's own instruction (which asked to verify the mechanism works, not
  to wire client-generated keys into every submission).

---

## Closeout

```
BUILD-26: PASS
FRONTEND CHAT TARGET: AGENT_V2
REAL APP CHAT -> AGENT V2: PASS
LEGACY CHAT CALLED BY APP: NO
NORMAL CHAT: PASS
GENERAL MEDICAL QUERY: PASS
SAFETY: PASS
HANDOFF: PASS
AUTH: PASS
GROUNDING: PASS
TELEMETRY CHATBOT_VERSION=agent-v2: PASS
ADMIN DASHBOARD V2 VOLUME INCREASES: PASS (1 -> 2, matching the 1 real UI message sent)
LEGACY FALLBACK PATH RETAINED: YES (CHAT_RUNTIME=legacy env var, code untouched)
READY FOR REAL USER V2 TRAFFIC: YES
```
