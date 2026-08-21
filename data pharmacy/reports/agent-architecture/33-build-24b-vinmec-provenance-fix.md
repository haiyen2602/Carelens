# BUILD-24B — Vinmec Provenance Honesty Fix

**Scope:** fix the P1 found live in BUILD-24 (report `32`): the model
labeling non-Vinmec evidence as "from Vinmec." Production stays at exactly
5% rollout throughout — not advanced, not rolled back. No legacy data
touched.

**Environment:** Railway production (`VMEC-04/BE`).

---

## 1. Root cause

Traced (BUILD-24, report 32 §4) to `synthesize_read_only`'s prompt in
`backend/agents/v2/model_gateway.py`: the model received the user's own
message (which might say "Vinmec") plus a JSON blob of tool evidence
carrying a raw `provenance` string like `"canonical-drug-v2:catalog"`, with
**no instruction anywhere telling it how to correctly describe that
provenance**, and — when Vinmec Web genuinely found nothing —
**no signal at all** that a Vinmec lookup had even been attempted and come
back empty. The model filled that gap by mirroring the user's own "Vinmec"
framing back into its answer.

## 2. Fix — three independent layers (defense in depth)

A prompt instruction alone is not an *absolute* guarantee against a model
that doesn't reliably follow it, so this is not a single fix:

1. **Proactive signal** (`backend/agents/v2/orchestrator.py`,
   `_NO_VINMEC_EVIDENCE_NOTE`): when intent is `VINMEC_WEB_INFORMATION` and
   Vinmec Web gathered zero evidence, an explicit system note is appended to
   the augmented message *before* the model answers, stating plainly that no
   Vinmec result was found and that any internal-tool-sourced answer must be
   labeled as internal/verified system data, never Vinmec.
2. **General provenance rule** (`backend/agents/v2/model_gateway.py`,
   `synthesize_read_only`): a standing instruction on every synthesis call
   (not just Vinmec-triggered ones) — only describe something as Vinmec-
   sourced if the evidence actually carries Vinmec Web provenance;
   `canonical-drug-v2:...` and internal RAG data must always be described as
   internal/verified system data; the user's own wording is never
   sufficient grounds by itself.
3. **Deterministic backstop** (`backend/agents/v2/orchestrator.py`,
   `_enforce_vinmec_provenance`) — **the actual enforced guarantee**. The
   orchestrator is the only place that authoritatively knows whether real
   Vinmec Web evidence was gathered for a run (a citation with
   `source == "vinmec-web"`, added only from a genuine
   `VinmecWebStatus.READY` result). After the model produces its reply: if
   the text mentions "vinmec" (case-insensitive) but no such citation
   exists, **the entire reply is replaced** with a fixed, honest fallback —
   never partially edited, since this codebase does not attempt to safely
   string-surgery a model's already-generated free text. This is intent-
   agnostic (also catches a hypothetical RAG-evidence mislabeling, not just
   the Vinmec-intent path) and touches only the `response` text field —
   `status`, `safety_decision`, `handoff_result`, and every checkpoint field
   are untouched, so **Safety authority is structurally unaffected by
   construction**, not just by care.

---

## 3. Regression suite (all 6 required scenarios)

New file `tests/test_agent_v2_vinmec_provenance.py` (15 tests) plus the
full existing Agent V2 suite:

| # | Scenario | Result |
|---|---|---|
| 1 | Vinmec query + real Vinmec evidence → may claim Vinmec + citation | PASS — unchanged from the existing `test_vinmec_web_query_preserves_provenance_and_citation`; re-verified from this file's own angle |
| 2 | Vinmec query + only canonical drug evidence → must NOT claim Vinmec | PASS — simulated the exact live misbehavior (model calls `search_drug`, synthesis text still says "Theo Vinmec..."); backstop replaces it with the honest fallback, citations stay `()` |
| 3 | Vinmec query + zero evidence → honest no-Vinmec response | PASS |
| 4 | Normal `search_drug` (unrelated to Vinmec) → correct canonical provenance, unaffected | PASS — reply passes through unmodified, no "vinmec" substring, guard is a no-op |
| 5 | RAG evidence → not mislabeled as Vinmec | PASS — simulated mislabeling caught by the same intent-agnostic backstop |
| 6 | Safety/Handoff/Auth/Idempotency → no regression | PASS — full existing suite (120 tests across orchestrator, transaction durability, checkpoints, doctor handoff, route, idempotency, safety-policy-review-workflow) plus the 15 new tests: **135/135 passing**, zero failures |

Broader sweep (`-k "agent_v2 or orchestrator or vinmec"`, excluding
unrelated pre-existing environment gaps): **270 passed, 3 skipped**
(Postgres-only tests requiring disposable DB env vars not set locally — the
same known, pre-existing gap noted in every prior build).

---

## 4. Live reproduction of the exact BUILD-24 failure cases

Deployed to production (`AGENT_ROLLOUT_PERCENTAGE=5` and
`AGENT_RUNTIME_ENABLED=true` left completely unchanged throughout — this
patch touches synthesis/orchestrator text-correction logic only, never
routing, data, or Safety semantics). **Deployment timestamp:
`2026-08-20T05:50:50.955Z`** (recorded for pre/post metric comparison).

Both messages that produced a false Vinmec attribution in BUILD-24 were
re-sent verbatim, live, post-deploy:

```
"Tim tren mang Vinmec thong tin ve thuoc nay"       (no drug named)
"Vinmec co thong tin gi ve thuoc paracetamol khong" (paracetamol named)
```

Both now return, identically:

```json
{
  "status": "COMPLETED",
  "reply": "Minh khong tim thay ket qua tra cuu Vinmec cho cau hoi nay. Neu ban
             muon, minh co the tra cuu thong tin thuoc tu du lieu noi bo da duoc
             xac minh (khong phai tu Vinmec) -- hay cho minh biet ten thuoc cu
             the ban can.",
  "citations": []
}
```

**0 fabricated source claims** in both live reproductions (was 2/2 before
this fix). `search_drug` is still called by the model (visible in `tools`)
— the fix does not stop the model from using internal data, only stops it
from mislabeling that data's source.

### Live regression, same session, post-deploy

| Check | Result |
|---|---|
| Safety SAFE (real reviewed policy, real MISSED occurrence) | `200 COMPLETED SAFE` |
| Safety SAFETY_BLOCKED (not-yet-due occurrence) | `200 SAFETY_BLOCKED` |
| HANDOFF_REQUIRED → HANDOFF_CREATED | `200 HANDOFF_CREATED` |
| Idempotency retry | Identical response |
| Duplicate handoff prevention (3 concurrent) | Exactly 1 `handoff_id` |
| Cross-patient authorization denial | `403` |
| Normal drug info (no Vinmec mention) | `COMPLETED`, correct reply, no "vinmec" substring |
| RAG/general medical query | `COMPLETED`, `citations: []`, no "vinmec" substring |

Zero regressions.

---

## 5. Observation window — not reset

Per this build's own instruction: the window is only reset if the patch
changed routing, data, or Safety semantics. It did not — `_enforce_vinmec_
provenance` only ever touches `RunResult.response` text; every other field
(`status`, `safety_decision`, `handoff_result`, all checkpoint state, the
rollout-percentage bucketing logic, the canary allowlist, all production
data) is untouched by this build. The 5%-since-BUILD-24 observation window
continues uninterrupted. Anyone comparing metrics before/after this patch
should use `2026-08-20T05:50:50.955Z` as the dividing line.

---

## Closeout

```
BUILD-24B: PASS
PROVENANCE HONESTY: PASS
VINMEC MISLABEL REPRODUCTION: FIXED
FABRICATED SOURCE CLAIMS: 0/2 (both live BUILD-24 reproduction cases re-tested post-patch, 0 fabricated claims; was 2/2 before this fix)
SAFETY REGRESSION: PASS
AUTH REGRESSION: PASS
5% ROLLOUT: ACTIVE
OBSERVATION STATUS: continuing, not reset (deployment at 2026-08-20T05:50:50.955Z is a semantics-preserving patch -- see Section 5); still short of the 48h/sufficient-organic-sample bar from BUILD-24
READY FOR 20%: NO (observation window still needs to actually elapse; this was the blocking P1 from BUILD-24 and it is now resolved, but the time/sample-size requirement is independent of this fix)
```
