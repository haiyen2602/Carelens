# BUILD-27 — BUDGET_EXCEEDED fix: "Ngày mai tôi cần uống thuốc gì"

**Scope:** reproduce, trace, and fix a production `BUDGET_EXCEEDED` report
on the query "Ngày mai tôi cần uống thuốc gì" (what medication do I need to
take tomorrow), without raising the token budget.

---

## 1. Reproduction (real, not mocked)

Seeded a synthetic patient (`budget-repro-patient-1`) with an **ordinary**
60-day, 2-drug chronic regimen (e.g. a metformin/losartan-shaped schedule:
one drug 3x/day, one drug 2x/day, sharing two of the three daily times) via
the real production write path (`tao_phac_do` + `duyet_phac_do` +
`generate_prescription_dose_occurrences` — the exact same code every real
prescription approval runs). Ran the real in-process `AgentOrchestrator`
(real OpenAI model, real tools, real local Postgres) for the exact reported
message — no HTTP layer skipped except auth (irrelevant to this bug), no
step mocked.

```
STATUS=BUDGET_EXCEEDED
INTENT=DRUG_INFORMATION   (see §5 — a separate, pre-existing router gap)
TOOLS_CALLED=['get_today_doses', 'get_upcoming_doses']
  get_upcoming_doses: 179 items, 131,072 JSON chars
  get_today_doses:      3 items,   2,209 JSON chars
METRICS: input_tokens=60,924  output_tokens=232  token_total=61,156
CONFIGURED_TOKEN_BUDGET=4,096
REPLY: "Agent run vuot gioi han token."
```

Reproduced on 100% of runs against this patient (not intermittent) — a
14.9x overrun on an ordinary prescription, not a pathological edge case.

## 2. Trace

- **Routed intent:** `DRUG_INFORMATION` (the router's fallback branch — see
  §5; a bare "ngày mai" phrase does not currently match
  `_UPCOMING_KEYWORDS`). This did not block reproduction: the model reaches
  for `get_upcoming_doses` regardless of which intent routed the run.
- **Tools called:** `get_upcoming_doses` (and non-deterministically
  `get_today_doses` / `get_active_prescriptions` alongside it — the
  model's own tool-choice is not perfectly deterministic between runs, an
  already-documented characteristic of this system from earlier builds).
- **Dose records returned:** `get_upcoming_doses` returned **179** dose
  groups — every future dose through the end of the entire 60-day
  prescription.
- **Context token count:** raw JSON evidence alone was 131,072 characters
  (~32,768 chars/4 naive estimate; real tokenization of UUID/timestamp-heavy
  JSON runs higher). Real measured cumulative usage across both model calls
  (plan turn + synthesis turn) was 60,924 input / 232 output / 61,156 total.
- **Configured budget:** `agent_token_budget=4096` (unchanged — see §4).
  `agent_max_tool_calls=6`, `agent_max_steps=6`, `agent_max_model_calls=2` —
  none of these guardrails tripped first; the token check is what fired.
- **Exact trip point:** `backend/agents/v2/runtime.py`'s post-synthesis
  check, `if metrics.token_total > self._limits.token_budget` — reached
  after the synthesis call had already sent the full 179-item evidence
  block as part of its input.

## 3. Root cause

**`backend/services/agent_read_only_tools.py::get_upcoming_doses`**:

```python
def get_upcoming_doses(self, *, patient_id: str) -> dict[str, Any]:
    now = self._as_utc(self._now())
    return {"items": [self._dose_group(group) for group in self._groups(patient_id) if group.scheduled_at >= now]}
```

Unlike `get_today_doses` (bounded to exactly one calendar day), this had
**no upper bound at all** — `scheduled_at >= now` returns every future dose
group through the end of the patient's entire prescription. The write path
(`generate_prescription_dose_occurrences`) materializes the full remaining
schedule up front at approval time, so any chronic prescription longer than
a few days produces a large, monotonically-growing result here. The tool's
own declared description to the model, `"Read the authorized patient's
upcoming doses."`, never promised the full remaining prescription either —
this was an unbounded-by-omission bug, not an intentional contract.

**Checked and ruled out:**

- **(A) Duplicate/stale dose data:** checked directly against the seeded
  patient's `dose_occurrence` rows — zero duplicate `generation_key`
  values, exactly the expected count for a clean 60-day/2-drug regimen (180
  groups: two drugs sharing 2 of 3 daily times, correctly merged into
  shared groups by the existing "one photo, one dose_event" design). Not
  present here. (BUILD-22's report 27 previously found this exact failure
  *mode* — duplicated seed-script rows tripping the same budget check — but
  that was a test-fixture bug, not a product defect, and unrelated data. The
  actual production patient behind this report was not checked for
  duplicates directly — I do not have that patient's id; a read-only check
  script is included in §6 for whoever does.)
- **(C) Context compaction/budget bug:** no evidence of one. The overrun is
  fully and directly explained by the raw evidence payload size; the
  Context Manager (RAG/retrieval budget trimming) is not even in the loop
  for `DRUG_INFORMATION`/`UPCOMING_DOSES` (`use_retrieval=False` for both).
- **(D) Legitimate budget too low:** not needed as an additional fix — see
  §4's real post-fix numbers, which land with 20-40%+ headroom under the
  unchanged 4,096 budget.

**Classification: B — tool returns an unnecessarily large payload.**

## 4. Fix (smallest safe change; token budget untouched)

Bounded `get_upcoming_doses` to a short forward window, calendar-date based
(so "tomorrow" is never clipped by what time it currently is):

```python
def get_upcoming_doses(self, *, patient_id: str) -> dict[str, Any]:
    now = self._as_utc(self._now())
    horizon_date = now.date() + timedelta(days=self._upcoming_window_days)
    return {
        "items": [
            self._dose_group(group)
            for group in self._groups(patient_id)
            if group.scheduled_at >= now and group.scheduled_at.date() <= horizon_date
        ]
    }
```

New setting `agent_upcoming_doses_window_days` (default **1**, i.e. "today's
remainder + all of tomorrow"), same settings-driven pattern as every other
Agent V2 budget knob — tunable without a code change, not hardcoded.

The default was chosen **empirically**, not guessed: real repeat runs
showed wider windows still failed intermittently, because the model
sometimes calls `get_today_doses`/`get_active_prescriptions` alongside
`get_upcoming_doses` in the same run —

| window_days | items (this patient) | real token_total observed (repeat runs) | result |
|---|---|---|---|
| 7  | 21  | up to 7,161  | BUDGET_EXCEEDED |
| 3  | 9-11 | 4,001 – 4,829 | flaky (passed once, failed once — same code, same data) |
| 2  | 6-8 | 3,982 – 3,988 | passed, but only ~2.7% headroom |
| **1 (chosen)** | **2-5** | **2,437 – 3,256** | passed every run, 20-40%+ headroom |

`get_today_doses` is untouched. No DB schema change. No change to
`agent_token_budget`, `agent_max_steps`, `agent_max_tool_calls`, or any
other limit — per the explicit instruction not to raise the budget as this
fix.

**TOKENS BEFORE:** 60,924 input / 232 output / **61,156 total** (14.9x over
the 4,096 budget) — single-drug variant of the same repro measured 47,106 /
381 / 47,487 (11.6x over) as a corroborating data point.

**TOKENS AFTER:** 2,437 – 3,256 total across repeated real runs (worst
observed case: all three dose/prescription tools called together) — **well
under** the unchanged 4,096 budget.

## 5. Related finding, deliberately not bundled into this fix

`_UPCOMING_KEYWORDS` in `orchestrator.py` does not actually contain "ngày
mai" (tomorrow) despite a comment nearby claiming it does — this is why the
repro's own `INTENT` read `DRUG_INFORMATION`, not `UPCOMING_DOSES`. It did
not block this fix (the tool-size bug reproduces under either intent), but
it's a real, separate router gap worth its own investigation — filed as
`tasks/TASK-ROUTER-ngay-mai-upcoming-keyword-gap.md` rather than folded in
here, since a keyword change needs its own full golden-set regression pass
to rule out over-matching, and this build's scope was the token bug only.

## 6. Verification

- **Exact reported query, 3 repeat real runs (2-drug 60-day regimen):** all
  3 → `COMPLETED`, token_total 2,580 – 2,857.
- **Today's schedule regression** (`get_today_doses`, untouched code path):
  `"Hôm nay tôi cần uống thuốc gì"` against the same patient → `COMPLETED`,
  correctly lists exactly the 3 real dose groups scheduled today.
- **No duplicate doses:** zero duplicate `generation_key` values on the
  seeded patient (unique DB constraint + direct query, see below).
- **No safety/auth regression:** re-ran a real acute-danger scenario
  ("tôi vừa uống một lúc 15 viên panadol") against the pre-existing staging
  patient → still `HANDOFF_CREATED` / `safety=HANDOFF_REQUIRED` / handoff
  row created, byte-for-byte the same behavior as before this change (this
  fix never touches the safety/handoff path).
- **Latency/cost not materially worse:** post-fix runs completed in
  4.1s–5.7s per call (vs. 8.1s for the pre-fix pathological 61k-token call)
  — faster, not slower, since far less data is now serialized/read back.
- **New regression test suite** added:
  `tests/services/test_agent_read_only_tools_upcoming_bound.py` (5 tests —
  bounded-not-whole-prescription, tomorrow-never-clipped, excludes-already-
  passed, get_today_doses-unaffected, window-is-configurable) — all pass.
- **Full existing Agent V2 test suite** (`test_agent_v2_tools.py`,
  `test_agent_v2_orchestrator.py`, `test_agent_v2_synthesis.py`,
  `test_agent_v2_safety_occurrence_binding.py`, `services/scheduling/*`) —
  **99 passed**, no regressions.

Read-only SQL for whoever has the actual reported patient's id, to check
Classification A directly against production (not run by this build — no
production patient id was available here):

```sql
-- duplicate dose_occurrence rows for one patient
SELECT generation_key, count(*) FROM dose_occurrence
WHERE patient_id = :patient_id GROUP BY generation_key HAVING count(*) > 1;

-- orphan prescription_item rows (no dose_occurrence at all)
SELECT pi.* FROM prescription_item pi
WHERE pi.patient_id = :patient_id
  AND NOT EXISTS (SELECT 1 FROM dose_occurrence d WHERE d.prescription_item_id = pi.id);
```

## 7. Deployment

**Not yet deployed.** This report covers the local fix and its local
verification only, per the task's own scope (reproduce/trace/fix/verify
locally). No DB migration is needed (settings-only + application-logic
change). Ready to `railway up` to `VMEC-04/BE` once confirmed.

---

## Closeout

```
ROOT CAUSE: B - get_upcoming_doses had no upper bound (scheduled_at >= now,
  no ceiling); an ordinary 60-day/2-drug chronic regimen returned all 179
  future dose groups, exceeding the token budget on every run. Classification
  A (duplicate data) and C (compaction bug) checked and ruled out for the
  reproduced scenario; D (budget too low) not needed given post-fix headroom.
TOKENS BEFORE: 60,924 input / 232 output / 61,156 total (14.9x over the 4,096 budget)
TOKENS AFTER: 2,437-3,256 total across repeated real runs (well under 4,096)
FIX: bounded get_upcoming_doses to a calendar-date forward window
  (new setting agent_upcoming_doses_window_days, default=1), chosen
  empirically from real repeat-run data. agent_token_budget and every other
  limit left unchanged. get_today_doses untouched. No DB schema change.
BUDGET_EXCEEDED: FIXED (locally verified with real OpenAI calls; not yet deployed)
```
