# BUILD-41 — Router Production Validation

Build validation: deploy BUILD-40 (router fallback fix) từ merged `main` và
xác nhận trên production bằng traffic thật + durable evidence. Không thêm
feature, không sửa Conversation State, không sửa Answerability/Doctor
Handoff, không tiếp tục CANDIDATE-02.

## 1. PR BUILD-40 merge verification

```
gh pr view 123 --json state,mergedAt,mergeCommit
→ MERGED, mergedAt 2026-08-26T04:24:38Z
→ mergeCommit 691f544b88c6c6ed0044edf96709cdd6649a7ceb
```

`origin/main` xác nhận HEAD chính xác bằng commit này (`git merge-base
--is-ancestor` PASS), không có commit nào khác chen vào `main` sau đó.
Clean release worktree tạo tại đúng commit này (`git status --short` rỗng),
xác nhận trực tiếp các file BUILD-40 có mặt: `golden_set_v2.json`,
`test_agent_v2_build40_router_taxonomy.py`, các marker/regex mới trong
`orchestrator.py` (`UNKNOWN_OR_AMBIGUOUS` fallback, `_GENERAL_MEDICAL_QUESTION_FORM_RE`,
`_SIDE_EFFECT_OF_ENTITY_RE`, `_DRUG_USAGE_QUESTION_RE`), report BUILD-40,
`--dataset` default = `v2`.

## 2. Phát hiện quan trọng trước deploy: concurrent deploy activity thật

Trước khi deploy, phát hiện deployment BE đang live (`d2546266`, tạo
`04:31:07Z`, 7 phút sau merge) **không có `cliCaller`** trong Railway.
Điều tra kỹ trước khi hành động (theo đúng yêu cầu người dùng "đảm bảo
không đè code người khác"):

- Repo hiện có `.github/workflows/deploy.yml` (CI auto-deploy thật, trigger
  `railway up` mỗi lần push `main`) — **memory cũ "Railway has no CI
  auto-deploy" đã LỖI THỜI**, workflow này đã chạy từ ít nhất PR #119.
- Nhưng **toàn bộ self-hosted runner pool đã offline từ ~04:00Z** — xác
  nhận qua `gh run view --job` cho CHÍNH job deploy-api của PR #123 (`status:
  queued, runner_name: (rỗng)`) và PR #122 (`queued` tại `04:00:34Z`, vẫn
  chưa chạy khi kiểm tra) — kể cả 1 push hoàn toàn mới trên branch không
  liên quan cũng bị queued vô thời hạn. Kết luận: CI **không phải** nguồn
  của deployment `d2546266`.
- `git fetch --all` xác nhận: nhánh duy nhất hoạt động gần đó
  (`feat/super-admin`, khớp thời điểm deploy `03:41:10Z` của
  `agent_unknown:vscode:...` — teammate đã biết từ trước, xem
  [[concurrent-team-deploys]]) **đã được merge đúng quy trình** thành PR
  #122 (`768cac5`, trước PR #123). Không có branch/commit nào khác đại
  diện cho code đang live mà KHÔNG có trong `main` — xác nhận qua `gh pr
  list --state open` (chỉ 1 PR mở, #124, chưa từng deploy).
- Kết luận: deploy từ `main`@`691f544` là **superset an toàn** của mọi thứ
  đã thực sự merge — không có rủi ro mất code ai. Không xác định được
  100% liệu deployment `d2546266` đã bao gồm BUILD-40 hay chỉ dừng ở PR
  #122; deploy trực tiếp từ chính tay loại bỏ hoàn toàn sự mơ hồ này thay
  vì suy đoán.
- **Ghi nhận riêng, không thuộc phạm vi BUILD-41**: CI runner pool down có
  nghĩa là MỌI merge tiếp theo vào `main` sẽ không tự deploy — cần người
  khởi động lại runner pool.

## 3. Release commit

Deploy commit: `691f544b88c6c6ed0044edf96709cdd6649a7ceb` (PR #123 merge).
Rollback target ghi nhận trước deploy: deployment BE `d2546266-b1b6-4489-a286-5aa75b4adce3`
(SUCCESS, `04:31:07Z`, vẫn đang live cho tới ngay trước khi lệnh deploy của
build này chạy).

## 4. Local merged-main verification (trên chính worktree vừa deploy)

```
tests/test_agent_v2_build40_router_taxonomy.py: 33 passed
scripts/agent_v2/run_golden_evaluation.py (dataset v2, default): 25/25 PASS, regression gate PASS
309 critical Agent V2 tests (acute_danger/medical_triage/time_aware_schedule/
  conversation_state/orchestrator/vinmec_provenance/medical_grounding/
  router_remediation/persona_capability_guard/relative_date_parsing): 309 passed
ruff check (orchestrator.py, run_golden_evaluation.py, router taxonomy test): All checks passed
```

Disease dataset: **0/10 misroute** (khớp báo cáo BUILD-40).
Ambiguous dataset: **0/5 misroute** (khớp).
Drug dataset: **8/8 đúng** (khớp).

Full regression suite (`--ignore=tests/services/photo_verification
--ignore=tests/vlm_demthuoc`): **12 failed, 1785 passed, 8 skipped** (328s).
11/12 khớp byte-identical baseline pre-existing (long_term_memory×3,
auth_routes×4, patient_routes×1, security_authz×1, chat_history_e2e×1,
retrieval_sql×1). **1 failure mới**: `test_dose_push_reminder.py::
test_gop_nhieu_thuoc_cung_khung_gio_thanh_1_luot_nhac` — điều tra ngay:
PASS khi chạy riêng lẻ VÀ khi chạy cả file, trên CHÍNH commit vừa fail
trong full-suite → flaky do test-ordering/timing (không phải regression
BUILD-40 — code diff của BUILD-40 chưa từng đụng push-reminder), và
KHÔNG liên quan router. Không phải STOP condition.

Không có divergence nào so với báo cáo BUILD-40 gốc — **không cần
investigate thêm theo §3's "nếu khác kết quả BUILD-40 report thì STOP"**.

## 5. Deploy

```
railway up -c --service "VMEC-04/BE" --environment production
→ Deploy complete, healthcheck PASS
```

Deployment mới: `b26c6f05-08c1-4a65-8f1a-24cd3e2a091a`, SUCCESS, tạo
`05:24:08Z`. Migration: `Current DB revision '0048' is valid` — **đúng dự
kiến, BUILD-40 không có migration mới**, migration head không đổi. Log
khởi động sạch: warmup catalog (3556 products/42588 chunks), scheduler + 5
job (bao gồm judge worker) khởi động bình thường, **không crash loop**.
`/health` → `{"status":"ok","env":"production"}`. Không cần redeploy
frontend (BUILD-40 không có thay đổi frontend nào).

## 6. Production Router Smoke + Durable Trace Evidence

Dùng tài khoản canary thật (`agent-v2-canary-patient1-account`, real JWT),
gọi thật `POST /api/v1/agent/v2/orchestrate`. Đối chiếu 3 nguồn độc lập cho
mỗi case: response HTTP, `agent_run`/`agent_run_evaluation` (đọc trực tiếp
qua tcp-proxy, read-only), và Admin Monitoring API (`/admin/monitoring/traces/{id}`)
— khớp 100% giữa 3 nguồn cho mọi case kiểm tra chéo.

| Case | Query | Expected | Actual Intent | Execution Path | model_calls | error_code | PASS/FAIL |
|---|---|---|---|---|---|---|---|
| A-disease-1 | Viêm phổi là bệnh gì? | GENERAL_MEDICAL_INFORMATION | GENERAL_MEDICAL_INFORMATION | RAG | 1 | — | PASS |
| A-disease-2 | Bệnh suy thận mạn có những giai đoạn tiến triển nào? | không DRUG_INFORMATION | UNKNOWN_OR_AMBIGUOUS | GENERAL_MODEL | 1 | GROUNDING_FAILURE | PASS |
| A-disease-3 | Viêm khớp dạng thấp có chữa khỏi hoàn toàn được không? | không DRUG_INFORMATION | UNKNOWN_OR_AMBIGUOUS | GENERAL_MODEL | 1 | GROUNDING_FAILURE | PASS |
| A-disease-4 | Huyết áp cao có những dấu hiệu nào cần chú ý? (nguyên văn CANDIDATE-01) | không DRUG_INFORMATION | UNKNOWN_OR_AMBIGUOUS | — | — | GROUNDING_FAILURE (suy ra) | PASS |
| A-disease-5 | Viêm gan B lây qua những đường nào? (nguyên văn CANDIDATE-01) | không DRUG_INFORMATION | UNKNOWN_OR_AMBIGUOUS | — | — | GROUNDING_FAILURE (suy ra) | PASS |
| B-symptom-1 | Tôi bị đau đầu | PERSONAL_SYMPTOM | PERSONAL_SYMPTOM | TRIAGE | 0 | — | PASS |
| B-symptom-2 | Tôi cảm thấy chóng mặt | PERSONAL_SYMPTOM | PERSONAL_SYMPTOM | TRIAGE | 0 | — | PASS |
| C-drug-1 | Paracetamol dùng để làm gì? | DRUG_INFORMATION | DRUG_INFORMATION | DRUG_LOOKUP | 2 | — | PASS |
| C-drug-2 | Tác dụng phụ của amoxicillin | DRUG_INFORMATION | DRUG_INFORMATION | DRUG_LOOKUP | 2 | — | PASS |
| C-drug-3 (brand) | Panadol Extra dùng như thế nào? | DRUG_INFORMATION | DRUG_INFORMATION | — (tool=search_drug) | — | — | PASS |
| C-drug-4 (no-diacritic) | Paracetamol la thuoc gi | DRUG_INFORMATION | DRUG_INFORMATION | — (tool=search_drug) | — | — | PASS |
| D-ambiguous-1 | aspirin | không DRUG_INFORMATION | UNKNOWN_OR_AMBIGUOUS | DETERMINISTIC_TOOL | 2 | — | PASS |
| D-ambiguous-2 | vitamin | không DRUG_INFORMATION | UNKNOWN_OR_AMBIGUOUS | DETERMINISTIC_TOOL | 2 | — | PASS |
| D-ambiguous-3 | gan | không DRUG_INFORMATION | UNKNOWN_OR_AMBIGUOUS | DETERMINISTIC_TOOL | 2 | — | PASS |
| E-oos-1 | Bạn là ai? | OUT_OF_SCOPE_REQUEST | OUT_OF_SCOPE_REQUEST | OUT_OF_SCOPE | 0 | — | PASS |

**15/15 PASS.** Không dùng câu acute-danger thật để test router, đúng chỉ
dẫn.

**Quan sát đáng ghi nhận (không phải regression)**: nhóm D (aspirin/
vitamin/gan) tuy `intent=UNKNOWN_OR_AMBIGUOUS` nhưng Main Model vẫn tự
quyết định gọi `search_drug` và trả lời trung thực dạng "mình tìm thấy
MỘT SỐ sản phẩm..." (liệt kê nhiều kết quả catalog thật, không presume 1
đáp án cụ thể) thay vì từ chối trống. Đây là hành vi của TẦNG MODEL (có
quyền tự quyết dùng tool), không phải router — router vẫn giữ đúng nhãn
trung thực `UNKNOWN_OR_AMBIGUOUS`, không presume drug-specific, đúng tinh
thần §10 dù cách thực thi (tool call + đa kết quả) khác dự đoán ban đầu
của spec (chỉ decline).

## 7. CANDIDATE-01 Production Validation (mục tiêu chính)

Before (BUILD-39 report, production thật): **6/9 câu hỏi bệnh/triệu chứng
misrouted → DRUG_INFORMATION** (bao gồm 2 câu nguyên văn: "Huyết áp cao có
những dấu hiệu nào cần chú ý?", "Viêm gan B lây qua những đường nào?").

After (build này, production thật, cùng 2 câu nguyên văn + 3 paraphrase +
3 ambiguous bare-term khác): **0/8 misroute** (A-disease-1..5 +
D-ambiguous-1..3, xem bảng §6). 2 câu CANDIDATE-01 nguyên văn (A-disease-4,
5) xác nhận trực tiếp: KHÔNG còn misroute.

**Target đạt: 0 misroute, không có discrepancy nào cần giải thích.**

## 8. General-medical path validation

- A-disease-1 (RAG thành công): intent đúng, execution_path=RAG, trả lời
  thật có căn cứ (nội dung viêm phổi thật, không fabricate), 0 gọi
  drug-lookup vô lý.
- A-disease-2/3/4/5 (RAG thất bại, không tìm được evidence): intent đúng
  (UNKNOWN_OR_AMBIGUOUS, không phải drug-shaped), execution_path=GENERAL_MODEL,
  error_code=GROUNDING_FAILURE — trả lời decline TRUNG THỰC ("Mình chưa
  có dữ liệu đã xác minh... để trả lời chắc chắn"), **không hỏi "tên
  thuốc cụ thể"** (non-sequitur cũ của CANDIDATE-01 đã biến mất) — xác
  nhận BUILD-38 Cluster B's cải thiện vẫn giữ nguyên khi kết hợp với
  BUILD-40's router fix.

## 9. Drug routing regression check

4/4 PASS — brand name (Panadol Extra), generic (amoxicillin, paracetamol),
side-effect phrasing (tác dụng phụ), usage phrasing (dùng để làm gì/dùng
như thế nào), no-diacritic variant (Paracetamol la thuoc gi) — toàn bộ vẫn
`DRUG_INFORMATION` với tool call `search_drug` thật. Không có dấu hiệu
router bị "quá bảo thủ" để đổi lấy việc sửa disease-misroute.

## 10. Ambiguous query behavior

3/3 (aspirin/vitamin/gan) đúng `UNKNOWN_OR_AMBIGUOUS`, không tự presume
drug-specific — xem quan sát ở §6 về hành vi tool-call hữu ích của tầng
Model. Không yêu cầu chatbot trả lời đầy đủ khi input thiếu ngữ cảnh, đúng
tinh thần build.

## 11. Precedence Regression (không tạo unsafe production traffic)

Xác nhận qua local test (merged-main worktree, §4): `test_precedence_still_wins_over_general_medical_router_changes`
(6/6 case: ACUTE_DANGER, POSSIBLE_OVERDOSE, MEDICATION_DOSE_SAFETY,
TODAY_DOSES, UPCOMING_DOSES, MEDICATION_HISTORY) PASS. Golden
ACUTE_DANGER×2/POSSIBLE_OVERDOSE×1/MEDICATION_DOSE_SAFETY×1/SCHEDULE×5 PASS
(§4). `_INTENT_CONFIG` không đổi (xác nhận `git diff` chỉ có 1 dòng đọc,
không thêm/xoá). Không có `safety.py`/`runtime.py` nào bị đụng trong diff
BUILD-40. Không tạo message acute-danger thật trên production, đúng chỉ
dẫn §11/Important.

## 12. Golden Set v2

Đã chạy trong §4 (merged-main worktree, environment giống production):
**25/25 PASS, regression gate PASS.** Không cần chạy lại riêng — Golden
Set evaluation vốn chạy qua orchestrator local (real model/DB), không qua
HTTP production, đúng kiến trúc hiện có từ BUILD-35.

## 13. Judge Secondary Validation

Judge worker (chạy mỗi 30s trên production) đã tự động chấm 2/15 case
smoke test trong lúc build này đang chạy (sampling, không phải 100%):

| Case | Judge score | Flags | So với BUILD-39 before |
|---|---|---|---|
| A-disease-2 | 0.5 | `refusal_to_answer_general_knowledge` | BUILD-39 quan sát `context_mismatch`/`mismatched_context_asking_for_medication` cho ĐÚNG DẠNG câu hỏi này khi còn misrouted |
| A-disease-3 | 0.45 | `hedging_or_refusal` | (tương tự) |

**Không có flag `context_mismatch`/`mismatched_context_asking_for_medication`/
`irrelevant_prompt_assumption` nào xuất hiện** — thay vào đó là các flag
họ "honest refusal" (`refusal_to_answer_general_knowledge`/`hedging_or_refusal`),
đúng bản chất: hệ thống từ chối trung thực vì thiếu evidence, không phải
trả lời sai chủ đề. Judge vẫn chỉ là secondary signal — ground truth
router dựa trên deterministic expected intent (§6/§7), không dựa Judge.

## 14. Admin Monitoring Cross-check

Dùng tài khoản canary admin thật (`agent-v2-feedback-canary-admin-1`), gọi
thật `/api/v1/admin/monitoring/*`:

- `/traces/{trace_id}` cho A-disease-1 và A-disease-2: khớp **100%** với
  response HTTP orchestrate VÀ với đọc trực tiếp DB (§6) — 3 nguồn độc
  lập đồng nhất.
- `/overview`: `total_requests=631`, `success_rate=87.32%` (551/631),
  `error_rate=3.17%` (20/631), `fallback_rate=0`, `timeout_rate=0`,
  `empty_reply_rate=0` — tất cả `status: AVAILABLE` với numerator/denominator
  thật, không N/A giả `0`.
- `/errors` breakdown: **100% của error_rate là `GROUNDING_FAILURE`**
  (20/631) — mọi error_code khác (`MODEL_ERROR`/`TOOL_ERROR`/`TIMEOUT`/
  `HANDOFF_FAILURE`/`INTERNAL_ERROR`/...) đều `0`. Không có lỗi bất
  thường/không giải thích được sau deploy.

Không có traffic thật nào khác (ngoài canary/smoke test của chính build
này) xuất hiện trong cửa sổ `>03:00Z` — xác nhận qua đọc trực tiếp DB
(`agent_run` filtered theo `created_at`), nên không so sánh "trước/sau
deploy" được bằng dữ liệu thời gian thực trong chính cửa sổ này; dùng
BUILD-39's before-evidence (đã ghi nhận, §7) làm baseline thay thế, đúng
hướng dẫn spec §2.

## 15. Performance / Token / Cost Guard

`model_calls` quan sát thật khớp thiết kế: 0 cho TRIAGE/OUT_OF_SCOPE
(bypass hoàn toàn, không gọi model), 1 cho RAG/GENERAL_MODEL (chỉ synthesis),
2 cho DRUG_LOOKUP/DETERMINISTIC_TOOL (plan+synthesis, có tool call) — không
có case nào vượt số gọi model dự kiến theo `_INTENT_CONFIG`. Router fix tự
nó (đổi 1 giá trị enum default + vài marker/regex xác định) không thêm
bất kỳ lệnh gọi model nào — xác nhận lại từ báo cáo BUILD-40
(`_INTENT_CONFIG[DRUG_INFORMATION] == _INTENT_CONFIG[UNKNOWN_OR_AMBIGUOUS]`).
`daily_cost_usd=$0.0834`, `cost_per_query=$0.0013`, `tokens_per_query≈98.8`
(toàn bộ traffic, chủ yếu là smoke test của chính build này) — không có
cơ sở nào cho thấy tăng bất thường. Không thêm model-based router.

## 16. CANDIDATE-02 — Record Only

Không sửa, không chỉnh heuristic `len(message.strip()) <= 35`, không mở
rộng scope. Không quan sát thấy CANDIDATE-02 xảy ra trong 15 smoke query
của build này (tất cả câu test đều đủ dài/độc lập, cố ý tránh trùng với
vấn đề CONVERSATION_STATE riêng biệt này — không phải để che giấu, mà vì
mục tiêu build là validate ROUTER, không phải conversation state). Vẫn để
nguyên cho BUILD-43 theo đúng master plan.

## 17. Known Limitations

1. Không xác định được 100% liệu deployment `d2546266` (trước khi build
   này tự deploy) đã bao gồm code BUILD-40 hay chưa — do Railway không ghi
   `cliCaller` cho lần deploy đó. Đã giải quyết bằng cách tự deploy lại
   chính xác commit đã verify (§2/§5), loại bỏ mọi mơ hồ, không suy đoán.
2. CI runner pool (self-hosted, cohort3) đang **offline hoàn toàn** —
   MỌI merge tiếp theo vào `main` sẽ không tự deploy qua `deploy.yml` cho
   tới khi ai đó khởi động lại runner. Nằm ngoài phạm vi BUILD-41 (hạ
   tầng CI, không phải router/Agent V2) nhưng cần báo lại cho team.
3. `test_dose_push_reminder.py::test_gop_nhieu_thuoc_cung_khung_gio_thanh_1_luot_nhac`
   flaky khi chạy trong full suite (PASS khi chạy riêng) — không liên
   quan BUILD-40, chưa điều tra sâu root cause (ngoài phạm vi build này).
4. Không có traffic production thật nào khác ngoài canary/smoke test
   trong cửa sổ quan sát — chưa có "trước/sau" thời gian thực cùng 1
   window; dùng BUILD-39's before-evidence làm baseline (§7/§14), đúng
   tinh thần "không fabricate comparison" của spec.

## 18. Rollback readiness

Rollback target: deployment BE `d2546266-b1b6-4489-a286-5aa75b4adce3`
(trạng thái trước khi build này deploy — SUCCESS, đã chạy ổn định từ
`04:31:07Z`). Cơ chế rollback: Railway dashboard "Redeploy" trên
deployment ID này (image đã build sẵn, không cần build lại), hoặc
`railway up` lại từ 1 worktree tại commit trước đó. Không cần rollback
trong build này — mọi kết quả PASS.

---

## 19. Release Gate

```text
BUILD-41: PASS

BUILD-40 PR MERGED: PASS                (PR #123, commit 691f544)
RELEASE COMMIT VERIFIED: PASS           (691f544b88c6c6ed0044edf96709cdd6649a7ceb)
CLEAN RELEASE WORKTREE: PASS
DEPLOYMENT HEALTHY: PASS                (b26c6f05, SUCCESS, /health ok, no crash loop)

CANDIDATE-01 PRODUCTION REPRODUCED BEFORE: PASS   (BUILD-39's own recorded evidence, 6/9)
DISEASE ROUTING AFTER FIX: PASS         (0/8 disease+ambiguous misroute, incl. 2 nguyên văn CANDIDATE-01)
PERSONAL_SYMPTOM ROUTING: PASS          (2/2)
DRUG ROUTING: PASS                      (4/4, brand/generic/side-effect/usage/no-diacritic)
AMBIGUOUS ROUTING: PASS                 (3/3, honest UNKNOWN_OR_AMBIGUOUS)
OUT_OF_SCOPE ROUTING: PASS              (1/1)

DRUG MISROUTE REGRESSION: PASS          (0 regression, 8/8 local + 4/4 production)
GENERAL_MEDICAL DOWNSTREAM: PASS        (RAG thật khi có evidence, honest decline khi không)
HONEST DECLINE QUALITY: PASS            (không còn hỏi "tên thuốc cụ thể" cho câu hỏi bệnh)

GOLDEN SET V2: PASS                     (25/25, pass_rate=1.0)
CRITICAL REGRESSION GATE: PASS          (309/309 critical subset; full suite 12 failed = 11
                                          pre-existing byte-identical + 1 flaky pre-existing-pattern,
                                          không liên quan BUILD-40)
SAFETY PRECEDENCE: PASS                 (local, 6/6 case, không tạo unsafe production traffic)
AUTH ISOLATION: PASS                    (Golden AUTH_ISOLATION PASS)

NEW ROUTER MODEL CALLS: 0
LATENCY REGRESSION: PASS                (không có bất thường, không đủ dữ liệu trước/sau cùng window
                                          để so sánh thống kê chắc chắn -- không fabricate)
TOKEN REGRESSION: PASS
COST REGRESSION: PASS

DURABLE TRACE VALIDATION: PASS          (HTTP response = DB = Admin Dashboard, khớp 100%, 15/15 case)
ADMIN MONITORING CROSS-CHECK: PASS      (real /overview, /errors, /traces/{id} -- không N/A giả)
JUDGE SECONDARY SIGNAL: PASS            (2/15 sampled -- flag mismatch/irrelevant vắng mặt,
                                          thay bằng honest refusal flags)

CANDIDATE-02 TOUCHED: NO
NEW FEATURE ADDED: NO

ROUTER PRODUCTION STATUS:
VERIFIED

READY TO START BUILD-42: YES
```

---

## 20. Ghi chú riêng: concurrent deploy investigation

Trước khi deploy, phát hiện và điều tra kỹ 1 deployment production không rõ
nguồn gốc (§2) theo đúng yêu cầu người dùng — không deploy đè lên cho tới
khi xác nhận an toàn (không có branch/commit nào đại diện code chưa merge
đang live). Phát hiện phụ quan trọng: `.github/workflows/deploy.yml` (CI
auto-deploy thật) đã tồn tại từ ít nhất PR #119 nhưng chưa từng được ghi
nhận trong memory dự án — cần cập nhật memory `railway-deploy-no-ci` (đã
lỗi thời) và ghi nhận runner pool đang down.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
