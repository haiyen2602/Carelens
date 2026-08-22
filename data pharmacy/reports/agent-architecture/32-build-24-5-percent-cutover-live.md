# BUILD-24 — 5% Production Cutover (LIVE, OBSERVING)

**Scope:** turn on Agent V2 for exactly 5% of production traffic and begin
observation. **This build does not advance to 20%.** Legacy continues
serving the other 95% and every account not in the 5% bucket or on the
canary allowlist, unchanged. No legacy data touched.

**Environment:** Railway production (`VMEC-04/BE`, `VMEC-04/Postgres`).

---

## 1. Pre-flight (re-verified live, not assumed from prior builds)

| Check | Result |
|---|---|
| OpenAI key rotated (post-BUILD-23 incident) and working | PASS — still the BUILD-24 rotated key (safe suffix check only), confirmed live |
| BUILD-24A backup + checksum still present | PASS — same file, same SHA-256 (`402f38c2...df7fb`), untouched |
| Migrations = 0034 | PASS |
| Legacy healthy | PASS — `/health` 200, `/api/v1/chat` 401 for unauthenticated (not a crash) |
| V2 architecture/data healthy | PASS — corpus 14,447/14,423, catalog 3,556 drug_product, 1 REVIEWED policy, all unchanged |
| Rollback / kill-switch ready | PASS — confirmed `AGENT_RUNTIME_ENABLED=false` immediately before rollout |

---

## 2. Rollout

```
AGENT_RUNTIME_ENABLED=true
AGENT_ROLLOUT_PERCENTAGE=5
AGENT_CANARY_ALLOWLIST=<unchanged, 5 existing accounts>
```

Deployed, confirmed live.

### The mechanism itself, proven live (not just unit-tested)

Three new synthetic, non-allowlisted probe accounts were created
specifically to exercise the percentage boundary (ids chosen offline via
the exact `sha256(id) mod 100` formula the route uses, so their bucket
assignment was known before testing):

| Account | Bucket | Expected | Observed |
|---|---|---|---|
| `build24-percentage-probe-6` | 1 | admitted (< 5) | `200 COMPLETED` |
| `build24-percentage-probe-4` | 4 | admitted (< 5) | `200 COMPLETED` |
| `build24-percentage-probe-2` | 98 | excluded (>= 5) | `404` (identical to disabled) |

This is the first live confirmation that the BUILD-23 rollout mechanism
correctly routes real HTTP traffic by deterministic bucket, not just in
`tests/test_agent_v2_route.py`.

---

## 3. Monitoring results (this session's window)

| Dimension | Result |
|---|---|
| Sample size | ~30 requests total this session (canary allowlist accounts, 3 percentage probes, perf batch, functional regression) — see §5 for why this is not yet a meaningful population sample |
| Error rate | **0** unexpected errors. Every non-200 response was an expected `403` (cross-patient denial) or `404` (percentage-excluded probe / kill-switch check) |
| Empty reply rate | 0/20 scripted perf calls, 0 across all manual calls |
| P50/P95/P99 | drug_information 3.8s/4.6s/4.7s; today_doses 4.2s/8.0s/8.7s; prescription_multi_tool 5.7s/7.1s/7.4s; rag_query 11.6s/14.1s/14.5s — all `COMPLETED`, 0 errors, but noticeably higher than BUILD-21–23's baselines (e.g. today_doses p95 was ~3.5–4.0s in every prior build). Not error-inducing this session, but worth a second data point before treating as "just noise" — see §6 |
| Avg cost/request | **$0.001814** (25 real samples, range $0.0008–$0.0049) — consistent with every prior build (~$0.0017–0.0018) |
| TIMEOUT / BUDGET_EXCEEDED | **0 occurrences** |
| Safety SAFE | PASS — live, real reviewed policy, real `MISSED` occurrence → `SAFE`, `handoff_id: null` |
| Safety BLOCKED | PASS — not-yet-due occurrence → `SAFETY_BLOCKED` / `DOSE_NOT_YET_ASSESSABLE` |
| HANDOFF_REQUIRED | PASS — doctor-review bypass → `HANDOFF_CREATED` |
| Doctor Handoff duplicate prevention | PASS — 3 concurrent duplicate requests converged on exactly one `handoff_id` |
| Authorization | PASS — cross-patient query denied `403`; percentage-excluded probe denied `404` |
| Idempotency | PASS — identical retry returned the byte-identical response |
| Checkpoint | PASS — every run this session terminalized correctly (spot-checked; consistent with BUILD-23's 0-stuck-non-terminal finding) |
| Redaction / security | PASS — logs contain only `agent_run_id`/`trace_id`/component/event/tool_name/provenance/token counts/cost/latency; no message text, no reply text, no JWT |

---

## 4. A real finding — Vinmec Web mislabels non-Vinmec content as "from Vinmec"

Reproduced **twice**, independently, with different messages:

```
"Tim tren mang Vinmec thong tin ve thuoc nay" (no drug named)
  -> intent=VINMEC_WEB_INFORMATION, tools=["search_drug"], citations=[]
  -> reply: "Mình tìm được thông tin thuốc Tinecol từ nguồn Vinmec..."
     (an unrelated antifungal cream, not what was asked about)

"Vinmec co thong tin gi ve thuoc paracetamol khong"
  -> intent=VINMEC_WEB_INFORMATION, tools=["search_drug"], citations=[]
  -> reply: "Theo dữ liệu tra cứu Vinmec, hệ thống có các sản phẩm...
     Nguồn: dữ liệu tra cứu thuốc Vinmec từ kết quả tìm kiếm được cung cấp."
```

Traced both through raw logs by `trace_id`: in neither run does any Vinmec
Web component or span appear at all. The only real evidence gathered was a
`search_drug` tool call, logged with `provenance="canonical-drug-v2:catalog"`
— the file-backed Canonical V2 catalog (see BUILD-23 §2), **not** Vinmec Web.
`citations` correctly stayed empty both times (no *structured* fabricated
citation object was created — that specific, narrower guarantee held) — but
the model's own generated reply text asserts, in both cases, that the
content came "from Vinmec" / "theo dữ liệu tra cứu Vinmec" when it
demonstrably did not.

**This is a real defect, not a false alarm**: reproducible, traced to its
exact root (the Main Model apparently mirrors the user's own "Vinmec"
framing back into its answer regardless of which tool actually produced the
content), and it directly touches this build's explicit "không được
fabricate citation" requirement in spirit, even though the narrow
structural guarantee (the `citations` array) held both times.

**Severity assessment**: classified as **P1 (RAG quality / provenance
honesty)**, not **P0**, and not a **Safety/Auth/Data-integrity P1** as this
build's own rollback gate specifically scopes it (`Tinecol`'s dosage
form/route/strength being misattributed to Vinmec is not unsafe dosing
guidance, not an authorization bypass, and not corrupted/lost data) — so
this finding **does not trigger the automatic-rollback gate** as written.
It is, however, serious enough to be the single blocking reason this report
recommends against 20% before it's fixed. Per this build's explicit
instruction, **no architecture or prompt change was made to work around
this mid-cutover** — it is reported as found, not patched to make the
metric look better.

---

## 5. Honest limits of this session's observation

- **Sample size is small and not organic.** Every one of the ~30 requests
  this session came from accounts under this build's own control (the
  existing canary allowlist, the 3 new percentage-probe accounts, and the
  scripted perf batch) — none from real users who happened to land in the
  5% bucket on their own. No organic production traffic was observed
  falling into the bucket within this session's short real-world window,
  which is expected and not itself a red flag, but it means the
  error-rate/latency/cost figures above describe *synthetic* load, not yet
  *real* user behavior at 5%.
- **The 48-hour / sufficient-sample-size requirement is not met.** This
  build turned the rollout on and produced one session's worth of
  synthetic verification; it has not, and could not within one interactive
  session, run for 48 real-world hours or accumulate a statistically
  meaningful organic sample. The rollout is left **ACTIVE** so that real
  observation can actually accrue over time — turning it off now would
  reset the clock on the exact thing this build is supposed to start.

---

## 6. Recommendations before 20%

1. **Investigate and fix the Vinmec-mislabeling defect (§4)** — the
   highest-priority open item. Likely candidates: constrain the Main
   Model's synthesis prompt so it only claims a Vinmec source when Vinmec
   Web evidence was actually gathered (not simply because the user's
   message mentioned Vinmec), or block `search_drug` from being offered to
   the model at all when the router already classified `VINMEC_WEB_
   INFORMATION` and no real Vinmec evidence exists, forcing an honest "I
   don't have that from Vinmec" fallback instead.
2. **Let the 48-hour/sample-size window actually elapse** with the rollout
   left active, then re-run this same monitoring battery against
   accumulated real data before deciding on 20%.
3. The elevated P95 latencies in §3 are a single data point; watch whether
   this recurs on the next check before concluding it's a trend.

---

## Closeout

```
BUILD-24: OBSERVING
5% ROLLOUT: ACTIVE
SAMPLE SIZE: ~30 requests this session (synthetic/canary/probe only -- no organic real-user traffic observed yet, see Section 5)
OBSERVATION DURATION: <1 hour (this session only -- the required 48h/sufficient-sample-size window has not elapsed, see Section 5)
ERROR RATE: 0% (0 unexpected errors; all non-200s were expected 403/404)
EMPTY REPLY RATE: 0%
P95/P99: drug_information 4.6s/4.7s; today_doses 8.0s/8.7s; prescription_multi_tool 7.1s/7.4s; rag_query 14.1s/14.5s -- see Section 3 note on elevated latency vs. prior baselines
AVG COST/REQUEST: $0.001814 (25 samples, range $0.0008-$0.0049)
SAFETY: PASS
HANDOFF: PASS
AUTHORIZATION: PASS
IDEMPOTENCY: PASS
RAG: FAIL (see Section 4 -- reproducible Vinmec-source mislabeling; not a Safety/Auth/Data-integrity P1, does not trigger automatic rollback, but is a real, open finding)
P0/P1: P0=0; P1=1 open (Vinmec Web / search_drug provenance mislabeling, Section 4) -- not in the Safety/Auth/Data-integrity category the rollback gate targets, so rollout stays ACTIVE
LEGACY FALLBACK: PASS (unaffected; confirmed healthy throughout; kill-switch mechanism unchanged and still proven)
READY FOR 20%: NO (observation window not met; open P1 in Section 4 should be resolved first)
READY TO DELETE LEGACY DATA: NO
```
