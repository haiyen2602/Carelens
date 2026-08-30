# BUILD-47 — Durable Follow-up Classifier Observability

## 0. Precondition check

- Baseline commit: `ce41d80` (merge of PR #171 into `main`).
- Branch: `feature/BUILD-47-follow-up-observability`, cut from `main`, clean
  working tree at start.
- Alembic head at branch point: `0062`. Verified `0063` is the only new head
  (`grep` over every `down_revision` — no duplicate parent, no branch point).
- Agent V2 confirmed as the live path, not a dormant one: the BUILD-25
  comment in `backend/api/agent_v2_routes.py` states "Agent V2 is now 100% of
  production traffic and legacy chat is ~0%". The stale
  "disabled Agent V2 path" wording in older docstrings
  (`backend/agents/v2/context.py`) predates that cutover and was NOT trusted.

Precondition satisfied — proceeded.

## 1. Problem (audit before code)

The user reported that the chatbot's multi-turn memory "isn't working very
well" and proposed appending previous answers into the next prompt.

That proposal was audited and **rejected as a regression**, not adopted:
`backend/agents/v2/follow_up.py`'s own module docstring records that BUILD-43
deliberately REPLACED exactly that mechanism (`resolve_conversation_context`,
which regex-scanned raw short-term memory text) because it was brittle. The
current design classifies off the canonical durable state
(`ConversationState.active_topic` / `active_entity`), never raw memory text.
Re-introducing prompt-concatenation would undo BUILD-43.

The real, confirmed defect is one level up: **the follow-up decision has
never been measurable.**

`AgentOrchestrator.run()` already emits it every turn
(`orchestrator.py`, event `agent_context_resolution.completed`, attributes
`follow_up_category` / `follow_up_reason_code` / `inherited_topic` /
`inherited_entity`). Two independent mechanisms silently discarded all four:

1. **Sanitizer allowlist.** `_sanitize_attributes()`
   (`backend/agents/v2/observability.py`) drops any key not in
   `_ALLOWED_ATTRIBUTE_KEYS`. None of the four were listed, so only
   `final_router_intent` ever survived into the log line.
2. **Span persistence.** `_build_span_rows()`
   (`backend/api/agent_v2_routes.py`) only converts `agent_span.started` /
   `agent_span.finished` pairs and the two self-contained events
   (`agent_model.completed`, `agent_run.finished`) into `AgentRunSpan` rows.
   `agent_context_resolution.completed` carries no `latency_ms` and is
   therefore a "bare marker event" that never becomes a durable row — by the
   function's own explicit, deliberate policy.

Confirmed by exhaustive search: zero references to `follow_up_category`,
`TRUE_FOLLOWUP`, `TOPIC_SWITCH`, or `AMBIGUOUS_FRAGMENT` in
`admin_monitoring_routes.py`, `agent_monitoring_metrics.py`, or any DB column.
`result.follow_up_decision` IS read live in `agent_v2_routes.py`, but only to
drive in-request `TOPIC_SWITCH` state clearing — never written anywhere.

**Net effect:** there was no way, in logs or in the database, to answer
"how often does a real patient turn lose its conversation context?" That
question must be answerable with real numbers before any keyword-list
expansion or `ConversationState` refactor can be justified — otherwise the
fix would be aimed by guesswork.

## 2. Scope decision

This build adds **measurement only**. Explicitly deferred, pending the data
this build produces:

- Expanding `_DEICTIC_MARKERS` / `_ATTRIBUTE_KEYWORDS` / `_DRUG_ASPECT_KEYWORDS`.
- Letting `ConversationState` remember more than one recent entity/topic
  (audited as a moderate multi-file refactor: `conversation_state.py`,
  `orchestrator.py`'s singular `OrchestrationRequest` prior-state fields,
  `suggested_actions.py`, and ~6 sites in `agent_v2_routes.py` including the
  `TOPIC_SWITCH` wipe — not a one-line change).

Also explicitly out of scope by instruction: **no admin monitoring change.**
No endpoint, service, dashboard, or UI reads the new columns. They exist for
direct SQL analysis.

## 3. Design

Mirrors migration `0042` (BUILD-32), which solved the identical shape of
problem — real data computed correctly in code but reaching only an
unqueryable log line.

| Change | File |
| --- | --- |
| 4 keys added to the allowlist + `_SAFE_CODE` validation branch | `backend/agents/v2/observability.py` |
| 4 nullable columns + 1 index on `AgentRun` | `backend/db/models.py` |
| Additive, reversible migration `0062 -> 0063` | `migrations/versions/0063_agent_run_follow_up_observability.py` |
| Stamp the decision onto the run row | `backend/api/agent_v2_routes.py` (`_persist_durable_trace`) |

Three deliberate decisions:

- **`NULL`, never a fabricated category.** Turns that structurally never
  reach the classifier (schedule / safety / out-of-scope / doctor-review, and
  any turn already resolved by a suggested-action button) store `NULL`.
  Defaulting them to `STANDALONE_QUESTION` would poison the very distribution
  this build exists to measure.
- **`getattr(result, "follow_up_decision", None)`**, not attribute access.
  `_persist_durable_trace` is best-effort and wrapped in a broad
  `except Exception`; an `AttributeError` on a non-`OrchestrationResult`
  object would be swallowed and would silently cost that run its spans,
  evaluation, and cost row too — not just these four fields.
- **The value discipline is unchanged.** Widening the key allowlist could
  become a hole for free-text (e.g. a raw patient message) to reach telemetry.
  The two string fields are validated through the existing `_SAFE_CODE`
  regex, the same branch `final_router_intent` already uses; a malformed
  value is dropped, not stored. Locked by its own regression test.

## 4. Tests

New: `tests/test_agent_v2_build47_follow_up_observability.py` (9 tests, all
passing). Written **before** the fix per `adrs/0001-test-strategy.md`;
confirmed red first (6 failed / 1 passed), then green.

- Sanitizer: all four keys survive; malformed values still rejected; `None`
  passes through as `None`.
- `_persist_durable_trace`: stamps a `TRUE_FOLLOWUP` (inherited entity) and a
  `TOPIC_SWITCH` (lost context) decision; writes `NULL` for a no-decision
  turn; tolerates a result object with no `follow_up_decision` attribute.
- **Enum/regex lock:** every member of `FollowUpCategory` and
  `FollowUpReasonCode` is asserted to survive `_SAFE_CODE`. A future member
  added in a shape that regex rejects would otherwise vanish from telemetry
  exactly as silently as the four attributes did before this build -- the
  failure mode this build exists to eliminate, so it is locked rather than
  left to reviewer vigilance.
- **End-to-end seam:** a real `orchestrator.run()` (spy model gateway -- no
  network, no API cost) produces a real `OrchestrationResult`, and its
  `follow_up_decision` is asserted to land in the columns intact. The other
  tests feed a `SimpleNamespace`, which structurally cannot catch a mismatch
  between what the orchestrator actually emits and what the write path
  expects.

Regression: `test_agent_v2_build32_durable_observability.py`,
`test_agent_v2_build43_follow_up_resolution.py`, `test_agent_v2_follow_up.py`,
`test_agent_v2_conversation_state.py` — **63 passed**, including
`test_drug_aspect_keywords_and_labels_stay_in_sync`.

`ruff check` clean on all changed files.

### Full-suite controlled comparison

The whole suite was run twice under identical conditions — once at the
baseline commit `ce41d80`, once on this branch — and the sorted
`FAILED`/`ERROR` list diffed:

| | baseline `ce41d80` | this branch |
| --- | --- | --- |
| failed | 46 | 46 |
| errors | 74 | 74 |
| passed | 1903 | **1912** |

The failure/error list is **byte-identical** (`diff` reports no difference
across all 120 entries). The passed count rises by exactly 9 — this build's
own 9 new tests. **This build changes zero test outcomes.**

Those 46 + 74 pre-existing failures are environmental, not code defects:
`tests/conftest.py` builds its fixtures from `SessionLocal` (the real
database), but `Settings.database_url` resolves to the `.env` placeholder
`postgresql://.../dbname` unless `DATABASE_URL` is exported, so every
real-DB-backed test fails to connect. Running the suite with a real
`DATABASE_URL` was deliberately NOT done: those tests write real rows, and
the local `vmec04` holds seeded demo data and paid-for drug embeddings.

Separately, `test_agent_v2_deepeval_judge.py` cannot be collected locally at
all — `deepeval` is not installed in this environment.

## 5. Migration verified against real Postgres

Against the local `vmec04` database (not asserted from the file):

- `alembic current` → `0062` before, `0063 (head)` after.
- `\d agent_run` confirms all four columns plus
  `ix_agent_run_follow_up_category_created`.
- `alembic downgrade -1` runs clean and removes every trace (0 remaining
  `follow_up` references); re-upgrade returns to `0063 (head)`.

## 6. Intended use

```sql
SELECT follow_up_category, count(*)
FROM agent_run
WHERE follow_up_category IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC;
```

The signal to watch is the `STANDALONE_QUESTION` / `AMBIGUOUS_FRAGMENT`
share on turns a human would call a follow-up. A high share is the evidence
that would justify the deferred keyword expansion; a low share would mean the
classifier is fine and the real weakness lies elsewhere (most likely the
single-entity memory limit).

## 7. Known limitations

- **Forward-looking only.** Data exists from deploy time onward; historical
  runs stay `NULL` and are not backfilled or guessed.
- **No UI.** Reading requires direct SQL, by design (admin monitoring
  deliberately untouched).
- **Records the decision, does not judge it.** The columns show what the
  classifier decided, not whether that decision was *correct*. Establishing
  correctness needs labelled data — the golden set has only 2 multi-turn
  cases and grades `execution_path`/citations, not `FollowUpCategory`.
- **No behavior change.** Routing, safety, retrieval, and response text are
  byte-identical; every write is on the existing best-effort, post-commit
  path that already cannot affect a real reply.

## 8. File scope

```
backend/agents/v2/observability.py                                   (modified)
backend/api/agent_v2_routes.py                                       (modified)
backend/db/models.py                                                 (modified)
migrations/versions/0063_agent_run_follow_up_observability.py        (new)
tests/test_agent_v2_build47_follow_up_observability.py               (new)
chat-bot-build/build_cai_thien/BUILD-47-FOLLOW-UP-OBSERVABILITY-REPORT.md (new)
```

No file under `backend/api/admin_monitoring_routes.py`,
`backend/services/agent_monitoring_metrics.py`, or the frontend was touched.

## 9. Release gate

- Tests: **PASS** (7/7 new, 63/63 related regression).
- Lint: **PASS** (`ruff`).
- Migration up/down against real Postgres: **PASS**.
- **PR: NOT CREATED — intentionally.** Held at local commit on
  `feature/BUILD-47-follow-up-observability` at the requester's explicit
  instruction so they can test locally first. PR to `main` (reviewer:
  Trương Quốc Trường, per `GIT_WORKFLOW.md`) remains to be opened by them.
