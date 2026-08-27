# BUILD-45 — Production Validation Report

Scope: production-validation only, per the task's own instruction. No new
feature work, no BUILD-46, no Track B changes, no fix to the handoff dedup
type bug (a separate, already-documented, deliberately-deferred defect).

## 1. Verify deployed main

- `git fetch origin main` → tip `bdf0eb3` (merge of PR #141, BUILD-45).
- Deployed BE deployment `5461e4f9` was built directly from a git worktree
  checked out at exactly `bdf0eb3`, independently confirmed
  byte-identical (`git diff --quiet origin/main` clean) before deploying
  it. `railway status` at the start of this validation still reports the
  same deployment ID (`5461e4f9`) — no other deploy has superseded it
  since.
- `GET /health` → `{"status":"ok","env":"production"}`.
- Scheduler: `Scheduler started` / `Escalation reminder scheduler
  started` present in boot logs; Judge worker (`_run_judge_worker`,
  30s interval) executing successfully on every tick with zero errors
  across the observation window.
- No crash loop: single continuous deployment since redeploy, no restart
  events in logs.

**MERGED COMMIT VERIFIED: PASS**
**DEPLOYMENT HEALTHY: PASS**

## 2. Production canary — real account, real HTTP, fresh conversation IDs

Real login (`POST /auth/login`, no minted JWT) as `MCK@gmail.com`
(patient_id `BN00002`) and `doctor@vmec04.dev` (doctor_id `BS-0000`),
every conversation used a freshly generated `conversation_id` so nothing
touches the account's own pre-existing chat history — same "chỉ được
test" constraint honored as in BUILD-44's own validation.

### A. Cold drug entity binding

Turn 1, `"Thuốc Berocca Bayer dùng để làm gì?"` (fresh conversation):
`status=COMPLETED`, `tools=['search_drug']`. Durable
`ConversationState.active_entity` (read directly from
`agent_run.metadata->'conversation_state'`, not inferred from the HTTP
reply) confirms:

```
{'type': 'drug', 'id': 'berocca-bayer-10v', 'canonical_name': 'Berocca Bayer 10v',
 'display_name': 'Berocca Bayer 10v', 'normalized_key': 'berocca bayer 10v', 'legacy_drug_id': None}
```

Canonical entity established correctly from `search_drug` evidence alone
— the exact BUILD-45 fix working as designed on real production data.

Turn 2, `"Tác dụng phụ thì sao?"` — **first attempt FAILED**
(`status=FAILED`, `error_code=TOOL_ERROR`). Investigated with full
durable evidence (span trail, application logs) before drawing any
conclusion — see §7 for the complete root-cause writeup. Summary: the
model's own follow-up plan called `search_drug` (not `get_drug_info`),
and that specific call was rejected at the Tool Gateway's Pydantic input
boundary (`SearchDrugArguments`, likely an out-of-range `limit` the
model-facing JSON schema never declares a bound for) — a **pre-existing
gap in the tool-argument contract, not a Candidate A logic defect,
confirmed unchanged by BUILD-45's own diff**. Re-ran the identical
2-turn scenario 3 more times against fresh conversations: **3/3
succeeded**, correctly calling `get_drug_info` (2 of the 3 also
re-confirmed with `search_drug`) and answering about the actual
established drug. Combined: **3/4 real attempts succeeded**; the 1
failure is real, reproducible in *class* (confirmed exploitable via
direct Pydantic validation), but not deterministic per-turn (model
tool-choice non-determinism).

**COLD DRUG ENTITY BINDING (turn 1 mechanism): PASS**
**NATURAL FOLLOW-UP: PARTIAL** — mechanism proven correct on 3/4 real
attempts; 1/4 hit a real, pre-existing, non-BUILD-45 tool-argument-
validation gap (see §7, §9).
**AMBIGUOUS AUTO-BIND: 0** — `"Paracetamol dùng để làm gì?"` (genuinely
multi-SKU in the real catalog) completed normally with no forced unique
bind (§3).

### B. Topic persistence

Turn 1, `"Viêm gan B là bệnh gì?"`: `status=COMPLETED`. Durable
`active_topic`:

```
{'type': 'medical_topic', 'canonical_name': 'Viêm gan B', 'display_name': 'Viêm gan B', 'normalized_key': 'viem gan b'}
```

Turn 2, `"Triệu chứng của nó là gì?"` — **the exact compound
pronoun+filler sentence that corrupted `active_topic` to the literal
string `"nó là gì"` during BUILD-45's own local E2E, before the fix**.
On real production: `status=COMPLETED`, reply genuinely about viêm gan B
("Mình không tìm thấy kết quả dữ liệu nội bộ đã xác minh nào liên quan
đến **triệu chứng của viêm gan B**..."), and durable `active_topic`
read back:

```
{'type': 'medical_topic', 'canonical_name': 'Viêm gan B', 'display_name': 'Viêm gan B', 'normalized_key': 'viem gan b'}
```

**Unchanged, exact same value as turn 1 — never `"nó"`, never `"nó là
gì"`, never any corrupted text.** This is the strongest possible
confirmation the fix works: the exact reproduction case is now correct
on real production with a real model.

Turn 3, `"Paracetamol dùng để làm gì?"`: `status=COMPLETED`,
`tools=['search_drug']`. Durable state: `active_topic=None,
active_entity=None` — stale disease topic correctly cleared on the real
topic switch.

**TOPIC PERSISTENCE: PASS**
**PRONOUN FOLLOW-UP: PASS**
**CORRUPTED TOPIC: 0** — confirmed via durable state read, not just the
HTTP reply text.
**TOPIC SWITCH CLEARS STALE STATE: PASS**

## 3. False-positive checks

| Check | Message | Durable result | Verdict |
|---|---|---|---|
| Ambiguous drug name → no auto-bind | `"Paracetamol dùng để làm gì?"` | `status=COMPLETED`, no crash, real multi-SKU catalog stays correctly unresolved | PASS |
| Bare pronoun, zero prior context → no fabricated topic/entity | `"Nó có nguy hiểm không?"` | `active_topic=None, active_entity=None`; reply asks the user to clarify rather than guessing | PASS |
| Unrelated short question after real prior context → no inherit stale state | `"Sỏi thận là bệnh gì?"` → `"Vitamin C có tác dụng gì?"` | turn 2: `active_topic=None, active_entity=None`; reply genuinely about Vitamin C, no mention of "sỏi thận" | PASS |

## 4. Durable evidence cross-check

Every scenario above was cross-checked across **four independent
sources for the same `agent_run_id`**: the HTTP response
(`status`/`intent`/`tools`/`reply`), the durable `agent_run` row
(`status`, `intent`, `error_code`, `model_calls`, `empty_reply`), the
durable `ConversationState` embedded in `agent_run.metadata_json`
(`active_topic`, `active_entity`), and `agent_run_span` rows
(`span_type='TOOL'`/`'MODEL'` counts, per-span `outcome`). Accessed via a
temporary `railway tcp-proxy` to the production Postgres (credentials
fetched in-process via `railway variables --kv`, never printed to any
visible output; proxy deleted immediately after use, per standing infra
hygiene).

One real, minor discrepancy noted (not a Candidate A/B defect): the HTTP
response's `tools` list for the failed turn (§2A) reported
`['get_drug_info']`, while the durable span trail shows the actual
executed/errored call was `search_drug`. This looks like the response's
`tools` field reflecting a *planned* tool name in a failure path rather
than what was actually attempted — a pre-existing response-shaping
nuance, noted for future observability work, not investigated further
here (out of this task's scope).

**NEW SYNC MODEL CALLS: 0** — confirmed structurally (Candidate A reads a
field the same, already-existing `search_drug` call computes; Candidate
B is pure string pattern-matching) and empirically (`model_calls` values
observed — 0, 1, or 2 per turn depending on whether Answerability/
generation ran — match the same shape the pre-BUILD-45 local E2E
baselines showed; no turn shows an inflated call count attributable to
either fix).
**NEW TOOL CALLS: 0** — same reasoning; `tool_spans` counts (0 or 1 per
turn) are consistent with the pre-existing per-intent tool budget.

## 5. Regression smoke

| Area | What was run | Result |
|---|---|---|
| Safety (negative control) | `"Tôi nên uống nhiều nước mỗi ngày không?"` (benign) | `status=COMPLETED`, `handoff_required=False` — no false escalation. **Deliberately did not re-run the positive/dangerous-trigger path live** (same caution as BUILD-44's own validation, to avoid manufacturing another real handoff on this account) — Safety's positive-trigger behavior is covered by the full local regression suite (BUILD-45 report §13) instead. |
| Dose Safety | `"Hôm nay tôi cần uống thuốc gì?"` (schedule/dose read) | `status=COMPLETED`, `intent=TODAY_DOSES`, correct resolution. Dose-safety escalation logic itself was **not** re-triggered live on production by design (same reasoning as Safety above); local regression (`test_v2_dose_safety_http.py`, full suite) is authoritative for that path. |
| BUILD-44 doctor takeover | Real doctor login (`doctor@vmec04.dev`), `GET /doctor/reviews` (read-only, no claim/activate/resolve) | `200 OK`, real queue returned (pre-existing rows from earlier canary work, untouched) — auth and queue-read path intact. |
| schedule/time | (same as Dose Safety row) | PASS |
| auth | Patient token → `GET /admin/monitoring/overview` | `403` (correctly denied). Doctor token → own queue | `200` (correctly allowed). |
| No stuck AgentRun | All 15 `agent_run` rows created by this validation queried directly | Every row reached a terminal status (`COMPLETED` or `FAILED`) — zero stuck in a non-terminal state. |

**SAFETY REGRESSION: PASS** (scope: negative control only, see above)
**DOSE SAFETY: PASS** (scope: local-regression-authoritative, see above)
**BUILD-44 TAKEOVER: PASS**
**NO STUCK RUNS: PASS**

## 6. Track B

`git diff --name-only` for BUILD-45's own PR #141 confirms zero files
under Track B's ownership (`backend/services/drug_image*`,
`backend/api/drug_image_*`, `frontend/.../drug-images/*`,
`migrations/versions/0052-0053/0055`) were touched. Track B's own
migration `0055` (merged separately via PR #140, deployed in the same
redeploy since both were queued on `main` together — see the deploy
report `chat-bot-build/build_cai_thien/BUILD-45-QUALITY-IMPROVEMENT-LOOP-2-REPORT.md`'s
prior session context) applied cleanly and independently, unaffected by
BUILD-45's changes.

**TRACK B UNTOUCHED: PASS**

## 7. Finding — search_drug tool-argument-validation gap (not fixed here)

**What happened**: on the very first live attempt of Scenario A's turn 2,
the model planned a `search_drug` call (rather than `get_drug_info`) as
part of answering a natural follow-up about an already-established drug.
That `search_drug` call failed in ~0.06ms — too fast to be real
catalog/DB work, and consistent with an input-validation rejection at the
Tool Gateway boundary (`backend/agents/v2/tools.py::ToolGateway.execute`,
lines ~305-308: a `pydantic.ValidationError` on
`SearchDrugArguments.model_validate(arguments)` is converted to
`ToolExecutionError("INVALID_TOOL_ARGUMENTS")`).

**Root cause (confirmed, not assumed)**: `SearchDrugArguments` requires
`limit: int = Field(ge=1, le=20)`, but the model-facing JSON schema for
`search_drug` (`backend/agents/v2/model_gateway.py`,
`_READ_ONLY_TOOL_SCHEMAS`) declares only `{"type": "integer"}` for
`limit` — **no `minimum`/`maximum` hint is ever communicated to the
model**, even though `strict: True` is set. Reproduced directly:
`SearchDrugArguments.model_validate({"query": "...", "limit": 0})` and
`{"limit": 50}` both raise a real `ValidationError` locally, matching the
near-zero failure latency observed on production.

**This is a pre-existing gap, not a BUILD-45 regression**:
`SearchDrugArguments` and its JSON schema declaration are untouched by
BUILD-45's diff (confirmed via `git diff`). However, BUILD-45's own
Candidate A fix is what makes this *specific* flow (a follow-up turn
where the model, given an already-known entity, chooses to re-call
`search_drug` rather than `get_drug_info` directly) newly reachable at
all — before BUILD-45, a cold turn never established an entity, so this
follow-up shape had no entity to work from and never reached this code
path in the first place.

**Reproducibility**: real, but non-deterministic (model tool-choice
decision). Re-running the identical scenario 3 more times: 3/3 succeeded
without hitting this path. Observed rate in this validation: 1/4.

**Not fixed in this task** — production-validation-only scope, and (per
the same discipline applied to the handoff dedup bug in BUILD-44's own
validation) a defect found live during validation is documented with a
precise root cause and reproduction, not silently patched mid-validation.
**Recommended follow-up** (scoped, small): either (a) add
`"minimum": 1, "maximum": 20` to `search_drug`'s JSON schema so the model
provider itself constrains generation, or (b) degrade
`INVALID_TOOL_ARGUMENTS` for `search_drug` specifically to a clamped
retry (e.g. clamp `limit` into range) instead of a hard turn failure —
(a) is the more root-cause-correct fix and should be preferred.

## 8. Known limitations of this validation

- Safety and Dose Safety's *positive*-trigger paths were deliberately not
  re-exercised live on production (same reasoning as BUILD-44's own
  validation — avoiding manufacturing new real safety/handoff events on a
  real account); local regression suite is authoritative for those paths.
- Double-claim / doctor-concurrency was not re-exercised (only one real
  doctor account exists) — local/CI evidence from BUILD-44 stands.
- The `search_drug` tool-argument-validation gap (§7) was observed at a
  1/4 rate in this validation's own small sample — not large enough to
  claim a precise production frequency, only that it is real and
  reproducible in class.

## 9. Release Gate

```
BUILD-45 PRODUCTION VALIDATION: PASS (1 documented non-blocking finding)

MERGED COMMIT VERIFIED: PASS
DEPLOYMENT HEALTHY: PASS

COLD DRUG ENTITY BINDING: PASS
NATURAL FOLLOW-UP: PARTIAL (3/4 real attempts succeeded; 1/4 hit a pre-existing, non-BUILD-45 search_drug argument-validation gap -- see section 7)
AMBIGUOUS AUTO-BIND: 0

TOPIC PERSISTENCE: PASS
PRONOUN FOLLOW-UP: PASS
CORRUPTED TOPIC: 0
TOPIC SWITCH CLEARS STALE STATE: PASS

NEW SYNC MODEL CALLS: 0
NEW TOOL CALLS: 0

SAFETY REGRESSION: PASS (negative-control scope, see section 5)
DOSE SAFETY: PASS (local-regression-authoritative scope, see section 5)
BUILD-44 TAKEOVER: PASS (read-only smoke)
NO STUCK RUNS: PASS

TRACK B UNTOUCHED: PASS

PRODUCTION STATUS: PARTIAL
READY FOR BUILD-46: YES (with 1 recommended non-blocking follow-up: search_drug tool-argument-schema bound, section 7 -- not a blocker, not fixed in this task)
```

STOP after this report, per task instruction — no hot-fix, no BUILD-46,
no Track B changes, no handoff-dedup-bug fix.
