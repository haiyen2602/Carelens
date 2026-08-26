# BUILD-40 — Router Quality Improvement Loop

Mục tiêu: sửa lỗi hệ thống khiến câu hỏi bệnh/triệu chứng bị phân loại sai
thành `DRUG_INFORMATION` (CANDIDATE-01, ghi nhận ở BUILD-39 §16). Build này
KHÔNG đổi retrieval, Safety, Judge, hay generation logic — chỉ router
(`classify_intent()`/`_is_medication_information_query()` trong
`backend/agents/v2/orchestrator.py`).

## 1. Precondition — PR #121 (BUILD-39) merged

```
gh pr view 121 --json state,mergeCommit
```
→ `MERGED`, merge commit `1a613e7828403ab3028f3db8efbf332079ce4a69`. Branch
`build-40-router-quality-improvement` tạo từ `main` sau merge, không phải
từ branch feature của BUILD-39.

## 2. Router audit (trước khi sửa code)

Đọc toàn bộ `classify_intent()` (dòng 580-684) và
`_is_medication_information_query()`. Thứ tự precedence xác nhận:
`ACUTE_DANGER_ESCALATION` → `POSSIBLE_OVERDOSE` → `MEDICATION_DOSE_SAFETY`
→ `DOCTOR_REVIEW` → `MISSED_DOSE`/`DELAYED_DOSE` → `PERSONAL_SYMPTOM` →
`DOSE_STATUS` → `OUT_OF_SCOPE_REQUEST` → (time-scoped schedule) →
`PRESCRIPTION_INFORMATION` → `VINMEC_WEB_INFORMATION` →
`_is_medication_information_query()` → general-medical
keyword/regex/topic-switch → greeting → **terminal fallback**.

**Root cause tìm thấy (không phải giả thuyết ban đầu)**: giả thuyết đầu
tiên — `_is_medication_information_query()` quá rộng, bắt nhầm từ vựng
bệnh lý — SAI, xác nhận trực tiếp bằng cách gọi hàm này trên cả 6 câu
CANDIDATE-01 thật: cả 6 đều trả về `False`. Đọc lại toàn bộ phần đuôi
`classify_intent()` mới lộ ra nguyên nhân thật: dòng cuối cùng (`else:`)
mặc định gán `DRUG_INFORMATION` cho BẤT KỲ message nào không khớp category
nào ở trên — không cần "giống" câu hỏi thuốc, chỉ cần trượt hết các check
khác. `UNKNOWN_OR_AMBIGUOUS` đã tồn tại sẵn trong `OrchestrationIntent`,
đã có decline-text riêng (BUILD-38 Cluster B `_GENERAL_MEDICAL_DECLINE_INTENTS`),
nhưng KHÔNG BAO GIỜ được `classify_intent()` gán — một giá trị enum "chết".

## 3. Failure taxonomy (không coi tất cả là 1 loại lỗi)

| Loại | Mô tả | Ví dụ | Fix |
|---|---|---|---|
| C — generic-question-falls-to-drug-default | Câu hỏi bệnh/triệu chứng chung trượt hết mọi keyword, rơi vào default sai | 6 câu CANDIDATE-01 | Đổi default `DRUG_INFORMATION` → `UNKNOWN_OR_AMBIGUOUS` |
| E — normalization/coverage gap | Dạng câu "là [1-2 từ] gì" chỉ khớp "là gì" 2 từ đúng nghĩa | "là bệnh gì", "là tình trạng gì" | `_GENERAL_MEDICAL_QUESTION_FORM_RE` |
| F — semantic classifier weakness (mặt thuốc) | Sửa (1) vô tình lộ ra 1 khoảng trống có sẵn: tên thuốc riêng không kèm từ "thuốc" chưa từng khớp evidence nào | "Paracetamol dùng để làm gì", "tác dụng phụ của amoxicillin", "Paracetamol dùng như thế nào", "uống trước hay sau ăn", "uống bao nhiêu viên" | `_UNAMBIGUOUS_MEDICATION_MARKERS`, `_SIDE_EFFECT_OF_ENTITY_RE`, `_DRUG_USAGE_QUESTION_RE`, `_SUSPECTED_SIDE_EFFECT_REPORT_MARKER` |
| A — disease-name-as-drug-entity | Không tìm thấy case thật nào trong dataset — mọi misroute quan sát được đều thuộc loại C, không phải do 1 tên bệnh bị nhận nhầm là tên thuốc | — | không cần fix riêng |
| D — precedence bug | Không tìm thấy — precedence đã đúng trước build này, xác nhận lại ở §5 | — | không đổi |

Không có loại nào cần "danh sách 6 câu literal" hay tăng ngân sách gọi
model — đúng ràng buộc §11 của spec.

## 4. Router design rule áp dụng

"Bằng chứng thuốc-cụ thể yếu (fuzzy match) không được thắng 1 câu hỏi y tế
rõ ràng." Cụ thể hoá bằng nguyên tắc: mọi evidence "unambiguous" (bỏ qua
gate câu hỏi-thông-tin) đều **loại trừ khi có mặt 1 generic-class marker**
(`_GENERIC_MEDICATION_CLASS_MARKERS`, ví dụ "thuốc giảm đau") — 1 bug thật
tự phát hiện trong lúc audit: `_UNAMBIGUOUS_MEDICATION_MARKERS` bản đầu
tiên (chứa "tác dụng phụ" trần) không tôn trọng exclusion này, khiến
"Tác dụng phụ của thuốc giảm đau là gì" (generic, phải ở lại
`GENERAL_MEDICAL_INFORMATION`) bị đẩy nhầm sang `DRUG_INFORMATION`. Sửa
bằng cách tách "tác dụng phụ" ra khỏi marker set trần, thay bằng
`_SIDE_EFFECT_OF_ENTITY_RE` yêu cầu cấu trúc "tác dụng phụ CỦA <X>" — 1
bệnh/tình trạng không có "tác dụng phụ", chỉ thuốc mới có, nên việc yêu
cầu phần bổ ngữ "của X" phân biệt đúng "tác dụng phụ của amoxicillin"
(thuốc) khỏi "nguyên nhân gây ra tác dụng phụ là gì" (câu hỏi chung, không
nêu thuốc nào — vẫn còn 1 test hồi quy sẵn có
`test_retrieval_dependency_failure_fails_closed_before_the_main_model`
xác nhận đúng `GENERAL_MEDICAL_INFORMATION` cho câu thứ 2).

Không có entity/DB lookup nào được thêm — toàn bộ vẫn là keyword/regex
xác định (deterministic), đúng kiến trúc router hiện có.

## 5. Precedence — không đổi, xác nhận lại bằng test

`test_precedence_still_wins_over_general_medical_router_changes`
(parametrize 6 case: ACUTE_DANGER, POSSIBLE_OVERDOSE,
MEDICATION_DOSE_SAFETY, TODAY_DOSES, UPCOMING_DOSES, MEDICATION_HISTORY)
— PASS cả 6. `_INTENT_CONFIG` không bị đụng trong diff (xác nhận bằng
`git diff | grep _INTENT_CONFIG` — chỉ xuất hiện ở dòng đọc, không có dòng
thêm/xoá).

## 6. Test dataset & multi-turn

File mới `tests/test_agent_v2_build40_router_taxonomy.py` (33 test):
nhóm A (bệnh chung → `GENERAL_MEDICAL_INFORMATION`, gồm accent/no-accent),
B (triệu chứng cá nhân → `PERSONAL_SYMPTOM`), C (thuốc tên riêng →
`DRUG_INFORMATION`), D (thuật ngữ trần mơ hồ → `UNKNOWN_OR_AMBIGUOUS`,
không presume thuốc), E (out-of-scope, không đổi), F (đúng 6 câu
CANDIDATE-01 thật), G (precedence, xem §5), H (follow-up ngắn không rơi
về DRUG_INFORMATION). Multi-turn: `test_short_general_medical_follow_up_never_falls_back_to_drug_information`
xác nhận "Thế còn tăng huyết áp?" (topic-switch tường minh) không rơi về
`DRUG_INFORMATION`; 2 case Golden thật (`GOLD-MULTI-001`,
`GOLD-DRUG-002` — hội thoại 2 lượt, lượt 2 là follow-up rút gọn) PASS
100% ở golden run cuối (§9).

## 7. Golden Set — version mới, không sửa v1 tại chỗ

`scripts/agent_v2/golden/golden_set_v1.json` giữ nguyên. File mới
`scripts/agent_v2/golden/golden_set_v2.json` (copy 23 case v1 +
`golden_set_version: "v2"`), thêm 2 case mới dưới category có sẵn
`RAG_GENERAL_MEDICAL` (không đổi `GoldenCategory` enum/
`GROUND_TRUTH_CONTRACT_VERSION`):
- `GOLD-ROUTER-001` — "Viêm phổi là bệnh gì?" → `RAG` thật, xác nhận bằng
  orchestrator thật trước khi khoá expectation (citations thật).
- `GOLD-ROUTER-002` — "Bệnh suy thận mạn có những giai đoạn tiến triển
  nào?" (paraphrase của CANDIDATE-01, không copy nguyên văn) →
  `GENERAL_MODEL` (honest-decline Cluster B), xác nhận bằng orchestrator
  thật.

Cả 2 câu cố ý >35 ký tự và xác nhận `_follow_up_category()` trả `None` —
tránh trộn lẫn với bug conversation-state riêng (xem §11). `run_golden_evaluation.py`'s
`--dataset` default đổi `v1` → `v2`; `.github/workflows/ci.yml`'s
`golden-smoke` job không truyền `--dataset` tường minh (tự động nhận v2)
và dùng `--deterministic-only` nên 2 case RAG mới + `DRUG_FOLLOWUP` không
chạy trong CI (không tốn API cost CI) — hành vi này không đổi so với
trước.

**GOLD-DRUG-002 (lượt 2, "Tác dụng phụ?")**: reclassify label-only.
Fragment trần không có "của X" nên router thấy `UNKNOWN_OR_AMBIGUOUS`
(§4's design rule), nhưng hành vi thật không đổi (`tool_names=["search_drug"]`,
`model_calls=2`, `status=COMPLETED` — xác nhận bằng `git stash`/`stash pop`
so khớp trực tiếp với code cũ). `execution_path` expected sửa
`DRUG_LOOKUP` → `DETERMINISTIC_TOOL` (label do `evaluation_v2.py`'s
`dispatch_evaluation()` yêu cầu `intent == "DRUG_INFORMATION"` chính xác
cho nhãn `DRUG_LOOKUP`) — không phải regression chức năng.

## 8. Baseline vs Post-fix — đo thật bằng git worktree (không đoán)

Chạy `classify_intent()` thật trên 1 dataset 29 câu (bệnh/triệu chứng/thuốc/
mơ hồ/safety/schedule/out-of-scope) với CODE CŨ (worktree tại commit
`1a613e7`, trước mọi thay đổi BUILD-40) và CODE MỚI (working tree hiện
tại), cùng 1 script, cùng 1 lần chạy:

| Category | N | Misroute → DRUG_INFORMATION TRƯỚC | Misroute → DRUG_INFORMATION SAU |
|---|---|---|---|
| Bệnh chung (disease) | 10 | 6 (60%) | **0 (0%)** |
| Triệu chứng cá nhân (symptom) | 3 | 0 | 0 (không đổi) |
| Thuật ngữ mơ hồ (ambiguous) | 5 | 5 (100%) | **0 (0%)** |
| **Tổng non-drug misroute** | **18** | **11 (61%)** | **0 (0%)** |
| Câu hỏi thuốc thật (drug) | 8 | 8/8 đúng | **8/8 đúng (không regression)** |
| Safety/Schedule/Out-of-scope | 3 | 3/3 đúng | 3/3 đúng (không đổi) |

Loại bỏ hoàn toàn misroute hệ thống trên dataset này, **0 regression** ở
nhóm drug-query thật — 4/10 câu bệnh trước đó đã đúng nhờ keyword "là gì"
có sẵn; 6/10 sửa nhờ default fix (§2); 2 câu ("là bệnh gì") sửa nhờ regex
mới (§3 loại E); 6 câu CANDIDATE-01 thật (không khớp bất kỳ keyword nào)
giờ honest `UNKNOWN_OR_AMBIGUOUS` thay vì sai `DRUG_INFORMATION`.

## 9. Golden Set — kết quả cuối

```
python scripts/agent_v2/run_golden_evaluation.py
25/25 cases passed (pass_rate=1.0)
Regression gate: PASS
```

(1 lần chạy trung gian gặp `TOOL_ERROR` thoáng qua ở `GOLD-DRUG-002` khi
chạy full-batch 25 case liên tục — reproduce lại bằng `--case-id
GOLD-DRUG-002` riêng lẻ thì PASS ngay, và chạy lại full batch lần nữa cũng
PASS 25/25 — kết luận: flake vận hành [rate limit/connection pool] khi
gọi API thật liên tục nhiều case, KHÔNG phải regression code — không có
thay đổi nào được thực hiện để "sửa" việc này.)

## 10. Judge secondary validation

`--with-judge` trên 2 case Golden mới (real Judge, không phải golden
router taxonomy — tránh tốn cost cho case đã có ground-truth xác định):

| Case | Query | Judge score | Flags | So với BUILD-39 (trước) |
|---|---|---|---|---|
| GOLD-ROUTER-001 | "Viêm phổi là bệnh gì?" (RAG thật) | 0.88 (relevance=1.0) | `[]` (rỗng) | — (case mới, không có "trước" vì trước đây sẽ bị misroute sang drug-shaped decline) |
| GOLD-ROUTER-002 | "Bệnh suy thận mạn có những giai đoạn tiến triển nào?" (paraphrase CANDIDATE-01) | 0.4 (relevance=0.2, honest decline) | `['abstention', 'unanswered_question']` | BUILD-39 quan sát cùng loại câu hỏi (misrouted) có flag `context_mismatch`/`mismatched_context_asking_for_medication` (report BUILD-39 §16) |

Xác nhận đúng yêu cầu §13: không có flag kiểu `irrelevant_prompt_assumption`
hay tương đương (`context_mismatch`/`mismatched_context_asking_for_medication`)
xuất hiện ở case sau fix — thay vào đó là `abstention`/`unanswered_question`,
đúng bản chất 1 honest-decline có chủ đích (Cluster B), không phải model
trả lời sai chủ đề. Không có flag an toàn mới nào xuất hiện ở cả 2 case.
Judge vẫn chỉ là secondary evidence — không dùng để quyết định pass/fail
chính (đã quyết định ở §8/§9 bằng dữ liệu determinstic).

## 11. Performance guard

`_INTENT_CONFIG[DRUG_INFORMATION] == _INTENT_CONFIG[UNKNOWN_OR_AMBIGUOUS]
== (None, False, False, False, False)` — xác nhận trực tiếp bằng Python,
giống hệt nhau ở mọi field (safety_trigger, requires_occurrence,
bypass_to_handoff, use_retrieval, use_vinmec_web). `_INTENT_CONFIG` bản
thân không nằm trong diff (`git diff | grep _INTENT_CONFIG` chỉ có 1 dòng
đọc, không thêm/xoá). Không có model call mới, không có router thứ 2,
không đổi ngân sách/timeout — toàn bộ fix vẫn là keyword/regex xác định,
0 gọi model để routing (giống trước). `GOLD-ROUTER-001`/`002` mỗi case chỉ
1 `model_calls` (synthesis), không có gọi phụ nào cho routing.

## 12. Regression — full suite

```
pytest tests/ --ignore=tests/services/photo_verification --ignore=tests/vlm_demthuoc
11 failed, 1781 passed, 8 skipped, 586 warnings in 302.02s
```

11 failure khớp CHÍNH XÁC (byte-identical theo tên test) với baseline
pre-existing đã ghi nhận ở BUILD-39 (`test_agent_v2_long_term_memory.py`
x3, `test_api/test_auth_routes.py` x4, `test_api/test_patient_routes.py`
x1, `test_api/test_security_authz.py` x1, `test_chat_history_e2e.py` x1,
`test_retrieval_sql.py` x1) — **0 regression mới**, không liên quan
router/BUILD-40. `--ignore` áp dụng cho 2 module VLM/pill-counting không
cài `cv2`/`numpy` trong môi trường này (không liên quan Agent V2, lỗi
collect-time từ trước, không phải test failure).

Zero-tolerance categories xác nhận PASS: ACUTE_DANGER (Golden +
`test_agent_v2_acute_danger.py`), POSSIBLE_OVERDOSE (Golden +
`test_agent_v2_medical_triage.py`), SCHEDULE_PAST/TODAY/FUTURE (Golden),
MULTI_TURN_CONTEXT (Golden `GOLD-MULTI-001`), AUTH_ISOLATION (Golden
`GOLD-AUTH-001`).

`ruff check` trên toàn bộ file đã đổi (`orchestrator.py`,
`run_golden_evaluation.py`, 3 file test đã sửa, file test mới) — All
checks passed. `golden_set_v2.json` không phải target lint Python (không
áp dụng ruff cho file JSON).

## 13. Known Limitations / Follow-up (không sửa trong build này)

1. **CONVERSATION_STATE bug tiền hữu (không phải BUILD-40)**:
   `resolve_conversation_context()`'s `_follow_up_category()` có heuristic
   `len(message.strip()) <= 35` khiến câu hỏi ngắn, đầy đủ ý (không phải
   fragment follow-up thật) bị coi là mơ hồ/thiếu ngữ cảnh, trả về
   `_context_clarification_reply()` thay vì câu trả lời thật. Xác nhận có
   từ trước BUILD-40 (đã ảnh hưởng `GENERAL_MEDICAL_INFORMATION` từ trước
   khi build này thêm `UNKNOWN_OR_AMBIGUOUS` vào tập trigger cùng cơ chế).
   BUILD-40 chỉ thêm 1 entry-point nữa vào CÙNG bug có sẵn (qua
   `UNKNOWN_OR_AMBIGUOUS`), không tạo ra bug mới. Đây chính là
   CANDIDATE-02 của BUILD-39, giờ đã xác nhận root cause — để lại cho
   build CONVERSATION_STATE riêng, không sửa lẫn trong build ROUTER này.
2. **Dạng câu "thông tin về [thuốc] X"** ("Cho tôi biết thông tin về thuốc
   paracetamol") không khớp bất kỳ marker nào (kể cả sau fix) — vì "thông
   tin về" là tiền tố dùng chung cho CẢ câu hỏi thuốc lẫn câu hỏi bệnh
   ("thông tin về bệnh tiểu đường"), không thể phân biệt bằng keyword
   không có entity lookup. Router sẽ trả `UNKNOWN_OR_AMBIGUOUS` (honest,
   không presume) — ghi nhận là 1 khoảng trống thật, không phải regression
   (dataset case thật không có ví dụ nào dạng này, chỉ phát hiện khi audit
   1 unit test mechanism không liên quan router).
3. **`vizicin` bare/1-từ không kèm câu hỏi**: theo đúng thiết kế §4/nhóm D
   của taxonomy test, giờ là `UNKNOWN_OR_AMBIGUOUS` — nhất quán với
   "aspirin"/"vitamin"/"gan". Test cũ `test_scenario_6_...` (BUILD-24D) đổi
   query từ "vizicin" trần sang "vizicin la thuoc gi" để giữ đúng mục đích
   gốc (Vinmec-mislabel correction), không đổi mục tiêu kiểm thử.

## 14. Production validation

CHƯA thực hiện trong build này — theo đúng thứ tự spec yêu cầu (LOCAL PASS
→ PUSH → PR → REVIEW → MERGE → DEPLOY). Sẽ thực hiện ở build validation kế
tiếp (theo mẫu BUILD-39) sau khi PR này được review và merge, không tự
động deploy từ build này.

---

## 15. Release Gate

```text
BUILD-40: PASS (local, chờ review/merge)

PRECONDITION (PR #121 MERGED): PASS   (1a613e7828403ab3028f3db8efbf332079ce4a69)
ROUTER AUDIT BEFORE CODE: PASS         (root cause thật xác nhận bằng test trực tiếp, không đoán)
CANDIDATE-01 REPRODUCED: PASS          (6/6 câu thật xác nhận DRUG_INFORMATION sai trên code cũ)

TAXONOMY FIX (không phải patch từng câu): PASS
  - default fallback: DRUG_INFORMATION -> UNKNOWN_OR_AMBIGUOUS
  - "là [1-2 từ] gì" generalization (regex, không phải danh sách bệnh)
  - unambiguous drug-entity markers + generic-class exclusion nhất quán

PRECEDENCE UNCHANGED: PASS             (6/6 case ACUTE/OVERDOSE/DOSE/SCHEDULE giữ nguyên)
NO NEW MODEL CALL: PASS                (_INTENT_CONFIG identical, xác nhận trực tiếp)
NO NEW ROUTER: PASS
NO HARDCODED 6 STRINGS: PASS           (taxonomy-level fix, generalize được ngoài 6 câu gốc)
SAFETY THRESHOLD UNCHANGED: PASS       (0 file safety/*.py bị đụng)

DISEASE MISROUTE ELIMINATED: PASS      (6/10 -> 0/10 disease dataset, 5/5 -> 0/5 ambiguous dataset)
DRUG QUERY REGRESSION: PASS            (8/8 -> 8/8, 0 regression)
SAFETY/SCHEDULE/OOS REGRESSION: PASS   (3/3 -> 3/3 không đổi)

GOLDEN SET v2: PASS                    (25/25, pass_rate=1.0)
MULTI-TURN REGRESSION: PASS            (GOLD-MULTI-001, GOLD-DRUG-002 PASS)
JUDGE SECONDARY VALIDATION: PASS       (flags mismatch/irrelevant vắng mặt sau fix; abstention/
                                         unanswered_question đúng bản chất honest-decline)

FULL REGRESSION SUITE: PASS            (11 failed = byte-identical pre-existing baseline, 0 mới,
                                         1781 passed, 8 skipped)
LINT: PASS                             (ruff check toàn bộ file đã đổi)

READY FOR PR: YES
```

---

## 16. Branch / PR

Branch `build-40-router-quality-improvement`, tạo sau khi PR #121 merge
vào `main`. Commit thay đổi router + test + golden set v2, push, mở PR,
**dừng lại theo đúng chỉ dẫn** — không tự merge, không tự deploy.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
