# BUILD-38 — Quality Improvement Loop

**Ngày**: 2026-08-25
**Nguyên tắc**: Audit trước, code sau. Ưu tiên theo evidence thật (production + Golden + Judge + Tickets), không đoán, không mở rộng feature theo cảm tính.

---

## 1. Audit

Audit dữ liệu thật từ production (qua `DATABASE_PUBLIC_URL` tcp-proxy, read-only) + local Golden/test suite + report BUILD-31→37. Production tại thời điểm audit: 606 `agent_run` (591 từ trước BUILD-37, +15 từ smoke test BUILD-37), 123 row từ **bệnh nhân thật** (BN00002/BN00028/BN00030/BN00055/BN00067/BN00068/BN00069 — không phải canary), 5 `agent_run_judge`, 3 `agent_feedback_ticket`, 1 `agent_safety_event`, 0 `agent_golden_run` (chưa ai persist golden trên production).

### A. Golden failures / weak categories
Golden set v1 hiện tại: 23/23 pass (baseline chạy lại trong build này, xem §6). Không có golden failure sống để audit — nguồn evidence chính là production + Judge.

### B/C. Judge low-score runs / dimension weaknesses
5 row Judge thật trên production, rubric `judge-general-medical` (4 row) + `judge-safety-handoff` (1 row):

| agent_run_id (rút gọn) | overall_score | relevance | flags |
|---|---|---|---|
| 3a1f46b1 | 0.55 | 0.2 | unhelpful_refusal, misaligned_followup_prompt |
| 327e585e | 0.65 | 0.4 | inappropriate_fallback_template |
| b3ab4b58 | 0.35 | 0.1 | unhelpful_refusal, irrelevant_context_mismatch |
| 50c609e7 | 0.30 | 0.1 | refusal_on_basic_query, irrelevant_clarification_request |
| 7e83e68c (safety) | 1.00 | — | (none — safety-handoff rubric riêng) |

**Cả 4 row rubric `judge-general-medical` đều có `relevance` thấp (0.1-0.4)** và flags đều xoay quanh cùng 1 chủ đề: câu trả lời honest-decline không phù hợp/không liên quan tới câu hỏi thật. Cả 4 đều là run `GENERAL_MEDICAL_INFORMATION`/`GROUNDING_FAILURE`.

### D. User feedback tickets
3 ticket production, đọc trực tiếp (sanitized bên dưới — không copy nguyên văn PII vào đây):
1. `agent-v2-timeaware-canary-patient-1`, WRONG_ANSWER, CLOSED — canary/synthetic, câu hỏi lịch tuần, không phải evidence chất lượng thật.
2. `agent-v2-timeaware-canary-patient-1`, WRONG_ANSWER, OPEN — `assistant_message` là **"test assistant reply text for BUILD-30 post-deploy regression check"** — artifact test thuần túy, KHÔNG phải model response thật, loại khỏi audit.
3. **`BN00028` (bệnh nhân thật), NOT_UNDERSTOOD, OPEN** — câu hỏi dạng "uống N viên vitamin C để tăng đề kháng được không", intent lúc đó = `DRUG_INFORMATION` (sai — đáng lẽ `MEDICATION_DOSE_SAFETY`). **Xác nhận qua git log: root cause đã được sửa bởi BUILD-29F (PR #107), merge 2026-08-23T10:03:33Z — 18 giờ SAU khi ticket này được tạo** (2026-08-22T16:18:29Z). Verify lại bằng `classify_intent()` thật trên code hiện tại: câu hỏi y hệt nay classify đúng `MEDICATION_DOSE_SAFETY`. **Không phải live issue** — ticket vẫn còn `OPEN` trên production (gap vận hành: không ai đóng ticket sau khi bug được sửa) nhưng không phải BUILD-38 code candidate.

### E. REVIEW_SUSPECTED_MISSED_RISK
Không có signal mới — cơ chế BUILD-34 vẫn nguyên vẹn, không đổi.

### F. Grounding failures
9/606 run có `error_code=GROUNDING_FAILURE` (tất cả từ dữ liệu cũ + BUILD-37 smoke test). Riêng bệnh nhân thật `BN00002`: **5/39 run (12.8%) là GROUNDING_FAILURE**, toàn bộ trong ngày 2026-08-25 (real, current usage). Đào sâu qua `agent_run_span`:
- 3/5 là `GENERAL_MEDICAL_INFORMATION` (có `RETRIEVAL retrieve` span, latency **6.4-12.2 giây** — xem Cluster A).
- 2/5 là `DRUG_INFORMATION` (không có retrieval span — Main Model không gọi tool nào, `tool_calls=0`).

### G. Fallback/error runs
`BUDGET_EXCEEDED` (9), `FAILED` (5), `TIMEOUT` (1) — toàn bộ từ 2026-08-19 đến 22, TRƯỚC BUILD-32, không phải issue hiện tại.

### H. Multi-turn context failures
Không có evidence thật (golden `GOLD-MULTI-001` pass; không có ticket/Judge signal về multi-turn). Không đủ evidence để chọn làm cluster.

### I. Drug lookup/entity-resolution failures
Không có evidence thật riêng biệt ngoài ticket đã lỗi thời (mục D.3) — không đủ evidence để chọn làm cluster riêng trong build này.

### J. Retrieval weak/empty cases — **EVIDENCE MẠNH NHẤT, ROOT-CAUSED CHÍNH XÁC**
Đo trực tiếp **TOÀN BỘ 10/10 `RETRIEVAL` span thật trên production** (không phải mẫu con): min=6.42s, max=12.23s, median=8.62s. **100% số lần retrieval thật đều chậm 6+ giây** — không phải outlier. Root-caused bằng `EXPLAIN (ANALYZE, BUFFERS)` trực tiếp trên production (read-only) + tái hiện y hệt trên local Postgres — xem Cluster A.

### K. Latency/cost anomalies liên quan quality
Latency retrieval (J) TRỰC TIẾP ảnh hưởng quality: user phải chờ 6-12s trước khi nhận được câu trả lời (kể cả khi câu trả lời cuối là honest decline) — latency cao là một phần nguyên nhân trải nghiệm kém, không tách rời khỏi vấn đề chất lượng.

---

## 2. Quality Taxonomy

| issue_id | category | symptom | evidence | execution_path | sample | severity | reproducibility | root_cause hypothesis | confidence | proposed fix | regression risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ISSUE-01 | RETRIEVAL | RAG retrieval chậm 6-12s | 10/10 real span, EXPLAIN ANALYZE | GENERAL_MODEL/RAG | 10/10 | P1 (không sai kết quả, nhưng latency nghiêm trọng, ảnh hưởng mọi user hỏi general medical) | 100% tái hiện (local + prod) | Query planner bỏ qua GIN trigram index cho `word_similarity`/`<%` operator vì `word_similarity_op`/`similarity_op` (catalog function thật cho toán tử, KHÔNG phải `word_similarity()` hay gọi) có `COST=1` mặc định — đánh giá sai chi phí thật | **CONFIRMED** (EXPLAIN ANALYZE trực tiếp, không đoán) | `ALTER FUNCTION ... COST 100` (migration 0047) | Rất thấp — chỉ là cost hint cho planner, không đổi logic/kết quả/thứ tự operator |
| ISSUE-02 | GENERATION | Honest-decline reply không phù hợp câu hỏi non-drug | 4/4 Judge row thật, relevance 0.1-0.4, flags unhelpful_refusal/irrelevant_clarification_request/misaligned_followup_prompt | GENERAL_MODEL | 4/4 | P2 (không sai an toàn, nhưng chất lượng thấp có evidence Judge thật) | 100% (fixed string dùng chung cho mọi intent) | 1 fixed string dùng CHUNG cho 5 intent khác nhau trong `_GROUNDING_REQUIRED_INTENTS`, với clarification ask "cho biết tên thuốc cụ thể" — hợp lý cho DRUG_INFORMATION/PRESCRIPTION_INFORMATION/DOSE_STATUS nhưng vô nghĩa cho GENERAL_MEDICAL_INFORMATION/UNKNOWN_OR_AMBIGUOUS (câu hỏi không liên quan thuốc cụ thể nào) | **CONFIRMED** (đọc code + verify bằng Judge score trước/sau trên đúng văn bản) | Tách riêng reply text cho non-drug-shaped intents, giữ nguyên logic/trigger/an toàn | Rất thấp — vẫn 100% deterministic, 0 model call mới, 0 thông tin mới, chỉ đổi từ ngữ |
| ISSUE-03 | TOOL_SELECTION | DRUG_INFORMATION đôi khi 0 tool call | 2/5 grounding-failure của BN00002 | GENERAL_MODEL | 2/39 (BN00002) | P3 — chưa đủ evidence/tần suất để root-cause chính xác trong build này | Chưa xác nhận | Model đôi khi không gọi `search_drug`/`get_drug_info` dù intent là DRUG_INFORMATION — có thể là prompt/model quyết định, cần audit riêng | LOW (chưa root-cause) | Không sửa trong build này — follow-up candidate | N/A |
| ISSUE-04 | (không phải bug) | Ticket BN00028 dose-safety misroute | 1 ticket thật | — | 1 (lịch sử) | — | Đã tái hiện, ĐÃ SỬA | BUILD-29F đã sửa route (`_PROPOSED_DOSE_RE`/`MEDICATION_DOSE_SAFETY`), merge SAU thời điểm ticket tạo | **CONFIRMED đã sửa** — không phải BUILD-38 candidate | Không cần sửa gì thêm; đóng ticket vận hành (không phải code) | N/A |

---

## 3. Prioritization

```text
P0: Không tìm thấy evidence P0 thật (không có missed acute danger/overdose/
    cross-patient leak/schedule regression trong dữ liệu audit được).

P1: ISSUE-01 (Retrieval performance) — score = impact(cao, ảnh hưởng MỌI
    RAG query thật) × frequency(10/10=100%) × severity(P1) ×
    reproducibility(100%) ÷ risk(rất thấp, chỉ cost hint) = ưu tiên cao nhất.

P2: ISSUE-02 (Generation honest-decline mismatch) — score = impact(trung
    bình, chỉ ảnh hưởng nhánh grounding-failure) × frequency(4/4 Judge
    row có sẵn, nhưng tổng thể volume production còn thấp) ×
    severity(P2, không phải an toàn) × reproducibility(100%, deterministic)
    ÷ risk(rất thấp, vẫn 100% deterministic + không thêm claim y tế mới).

P3: ISSUE-03 (Tool selection cho DRUG_INFORMATION) — evidence chưa đủ
    (2 sample), KHÔNG chọn vào scope build này.
```

Không chọn ISSUE-03 dù "dễ audit thêm" — vì chưa đủ evidence (đúng nguyên tắc "Không chọn issue chỉ vì dễ sửa" / không đoán khi thiếu bằng chứng).

---

## 4. Selected Scope — 2 cluster

**Cluster A (ISSUE-01): Retrieval query performance.**
Evidence: 10/10 real production retrieval spans, EXPLAIN ANALYZE root-cause chính xác. Why now: ảnh hưởng MỌI RAG query thật, risk sửa cực thấp (chỉ 2 dòng SQL cost hint, không đổi kết quả). Expected impact: giảm 40-75% latency retrieval tùy hình dạng câu hỏi (đo thật, xem §6). Files: `migrations/versions/0047_pg_trgm_word_similarity_cost.py` (mới), `tests/test_retrieval_sql.py`.

**Cluster B (ISSUE-02): Generation honest-decline mismatch cho non-drug intents.**
Evidence: 4/4 real Judge row có relevance thấp + flags cụ thể trỏ đúng vào chính xác defect này (clarification ask không phù hợp). Why now: có Judge evidence thật, risk sửa thấp (vẫn deterministic, không có model call mới). Expected impact: cải thiện Judge relevance/flags cho nhánh GENERAL_MEDICAL_INFORMATION/UNKNOWN_OR_AMBIGUOUS grounding-failure — đo thật +0.10 overall_score, +0.10 relevance, loại bỏ flag `irrelevant_prompt_assumption` (xem §6). Files: `backend/agents/v2/orchestrator.py`, `tests/test_agent_v2_medical_grounding.py`.

**Risks (cả 2 cluster)**: Cluster A rủi ro gần như 0 (thuần cost hint DB, không đổi logic/kết quả — verify bằng test xác nhận `lexical_search()` trả về đúng số candidate như trước). Cluster B rủi ro thấp (chỉ đổi 1 fixed string cho 2/5 intent, không đổi trigger condition/logic an toàn/grounding enforcement — verify bằng 28 test cũ + 1 test mới đều pass).

**Không chọn thêm cluster thứ 3** — đúng giới hạn "tối đa 2-3 cluster", và ISSUE-03 chưa đủ evidence.

---

## 5. Root Cause Analysis (chi tiết)

### Cluster A — Retrieval performance

`backend/services/retrieval.py::lexical_search()` dùng `noi_dung_unaccent <% :query` (toán tử `word_similarity`, tìm đoạn văn tương tự trong nội dung dài). Toán tử `<%`/`%` KHÔNG dùng function `word_similarity()`/`similarity()` (nguời code hay gọi trực tiếp) mà dùng 2 catalog function riêng: `word_similarity_op`/`similarity_op` — cả 2 đều có `procost=1` mặc định (chi phí bằng 1 phép cộng số nguyên). Chi phí THẬT của trigram matching trên `noi_dung` (văn bản dài) cao hơn rất nhiều — nên planner luôn đánh giá sai, chọn `Index Scan using ix_drug_chunks_corpus_version` (btree KHÔNG liên quan gì tới trigram) rồi áp `word_similarity()` như filter trên TỪNG dòng (~14000+ dòng), thay vì dùng GIN trigram index thật đã tồn tại (`ix_drug_chunks_noi_dung_unaccent_trgm`).

Verify bằng `EXPLAIN (ANALYZE, BUFFERS)` **trực tiếp trên production** (read-only, qua tcp-proxy đã được cấp quyền từ BUILD-37):
```
BEFORE: Index Scan using ix_drug_chunks_corpus_version ... Execution Time: 8587.152 ms
```
Thử nhiều phương án khác trước khi chọn fix cuối: partial index mới (không đổi kết quả — planner vẫn không chọn), UNION/CTE tách 2 predicate (kết quả TỆ HƠN — xử lý dư thừa dòng của corpus_version sai), `enable_seqscan`/`enable_indexscan` OFF (không đổi — corpus_version vẫn là "Index Scan"/"Bitmap Index Scan" hợp lệ, không phải seq scan). **Chỉ `ALTER FUNCTION word_similarity_op/similarity_op COST 100` sửa đúng root cause** — planner tự động chọn `BitmapAnd` giữa `ix_drug_chunks_corpus_version` và cả 2 GIN trigram index.

### Cluster B — Generation honest-decline mismatch

`_enforce_medical_grounding()` áp dụng CHUNG 1 fixed reply (`_UNGROUNDED_ANSWER_DECLINE_REPLY`) cho 5 intent trong `_GROUNDING_REQUIRED_INTENTS` (`DRUG_INFORMATION`, `PRESCRIPTION_INFORMATION`, `DOSE_STATUS`, `GENERAL_MEDICAL_INFORMATION`, `UNKNOWN_OR_AMBIGUOUS`). Reply có câu "cho mình biết rõ hơn (ví dụ tên thuốc cụ thể)" — hợp lý cho 3 intent đầu (thật sự về 1 thuốc cụ thể), nhưng **vô nghĩa** cho 2 intent sau (câu hỏi y tế chung/mơ hồ, không nhất thiết về thuốc nào). Đúng khớp với flags Judge thật đã ghi nhận: `irrelevant_clarification_request`, `misaligned_followup_prompt`.

---

## 6. Baseline & Before/After

### 6.1 Baseline (trước fix, đúng nguyên tắc "immutable")

Chạy trên `git worktree` sạch tại `origin/main` (`195ed2c`), DB downgrade về migration 0046 (function cost = 1, chưa fix):
```
23/23 cases passed (pass_rate=1.0), Regression gate: PASS
Judge: scored 25 pending row(s)
Provenance: main_model=gpt-5.4-mini, judge_model=anxs/gemini-3.7-flash-high,
            golden_set_version=v1
Wall time: 15:19:43 -> 15:24:13 (4m30s)
```
Lưu tại `agent_golden_run`? KHÔNG — chạy trên worktree tạm, chỉ để so sánh baseline (không persist run tạm này vào bất kỳ DB nào để tránh gây nhiễu).

### 6.2 Sau fix (Golden, full 23 case, `--with-judge --persist`)

Chạy trên nhánh build này (2 fix đã áp dụng, DB đã upgrade lên 0047):
```
23/23 cases passed (pass_rate=1.0), Regression gate: PASS
Persisted run 20260825T152442Z to agent_golden_run/agent_golden_run_case (local)
Wall time: 15:24:42 -> 15:29:02 (4m20s)
```

**So sánh (`--baseline` real diff)**: 23/23 `UNCHANGED` (baseline_passed=true, candidate_passed=true cho toàn bộ 23 case) — **0 regressed, 0 improved ở mức pass/fail** (đúng dự kiến — golden set's RAG case đều crafted để có grounding thật, không đi qua nhánh honest-decline mà Cluster B sửa; Cluster A chỉ đổi tốc độ không đổi kết quả).

**Lưu ý phương pháp thật** (minh bạch, không giấu): cả 2 lần chạy đều dùng CÙNG git ref (`195ed2c`) vì thay đổi code của build này CHƯA COMMIT tại thời điểm đo (`git rev-parse HEAD` không phản ánh working-tree uncommitted) — baseline THẬT SỰ khác biệt nhờ: (1) chạy từ git worktree riêng KHÔNG có 2 fix trong working tree, (2) DB downgrade về migration 0046 (cost=1). Sau fix chạy từ working tree CÓ đủ 2 fix + DB tại 0047.

### 6.3 Cluster A — latency thật (đo bằng đúng app code `lexical_search()`, không phải giả lập)

```
BEFORE fix (migration 0046, cost=1):  8.621s, 50 candidates
AFTER fix  (migration 0047, cost=100): 5.034s, 50 candidates
```
**Giảm 41.6% thời gian, SỐ CANDIDATE Y HỆT (50=50)** — xác nhận fix không đổi kết quả tìm kiếm, chỉ đổi tốc độ. Đo qua `EXPLAIN ANALYZE` thuần SQL (không qua ORM) cho case cụ thể: 8587ms → 3090-4655ms tùy hình dạng truy vấn (isolated single-predicate vs full combined-OR query production dùng thật) — giảm 46-64%.

### 6.4 Cluster B — Judge score thật, trước/sau, cùng 1 câu hỏi thật

Scoring trực tiếp bằng Judge thật (không giả lập) cho đúng 2 văn bản (cũ production đã serve thật / mới sau fix), cùng query "Bệnh tiểu đường là gì?":

| | overall_score | relevance | clarity | flags |
|---|---|---|---|---|
| OLD (production, trước fix) | 0.35 | 0.1 | 0.6 | `unhelpful_refusal`, `irrelevant_prompt_assumption` |
| NEW (sau fix) | 0.45 | 0.2 | 0.9 | `unhelpful_refusal` |

**+0.10 overall_score (+28.6%), +0.10 relevance (gấp đôi), +0.3 clarity, loại bỏ hoàn toàn flag `irrelevant_prompt_assumption`** — đúng chính xác defect đã root-cause (clarification ask "tên thuốc cụ thể" không còn xuất hiện trong câu trả lời general-medical). `unhelpful_refusal` vẫn còn — **trung thực, không giấu**: đây vẫn là 1 lời từ chối (honest decline), Judge vẫn coi "từ chối" là chưa hoàn toàn hữu ích dù đã liên quan hơn — sửa triệt để đòi hỏi MỞ RỘNG corpus (thêm nội dung giáo dục y tế chung, không chỉ thông tin thuốc), một quyết định về DỮ LIỆU/phạm vi sản phẩm, ngoài phạm vi build này (đã ghi vào follow-up candidates §16).

---

## 7. Root cause confirmed / Fix is systemic / No phrase-by-phrase patching

- Cluster A: root cause là 1 THIẾT LẬP DATABASE sai (function cost), không phải patch riêng cho 1 câu hỏi — sửa 1 lần, áp dụng cho MỌI truy vấn `word_similarity`/`similarity` trong toàn hệ thống (không chỉ RAG, cũng áp dụng cho `fuzzy_name_search` nếu dùng cùng toán tử).
- Cluster B: sửa theo INTENT SHAPE (drug-shaped vs non-drug-shaped), không phải patch theo từng câu hỏi cụ thể — áp dụng cho TOÀN BỘ câu hỏi thuộc `GENERAL_MEDICAL_INFORMATION`/`UNKNOWN_OR_AMBIGUOUS` gặp grounding failure, không chỉ câu "tiểu đường".

---

## 8. Fix — Files Changed

- `migrations/versions/0047_pg_trgm_word_similarity_cost.py` (MỚI): `ALTER FUNCTION word_similarity_op/similarity_op COST 100`. Idempotent, reversible thật (downgrade đặt lại COST=1). Verify upgrade→downgrade→upgrade→no-op trên local Postgres thật.
- `backend/agents/v2/orchestrator.py`: thêm `_UNGROUNDED_GENERAL_MEDICAL_DECLINE_REPLY` + `_GENERAL_MEDICAL_DECLINE_INTENTS`, sửa `_enforce_medical_grounding()` chọn reply theo intent shape. KHÔNG đổi trigger condition/logic grounding/status/error_code.
- `tests/test_retrieval_sql.py`: 2 test mới (cost config guard + result-identity guard).
- `tests/test_agent_v2_medical_grounding.py`: tách 1 test parametrized thành 2 (drug-shaped giữ nguyên assertion cũ, non-drug-shaped assertion mới) + assert rõ "tên thuốc" không xuất hiện trong reply non-drug.

**KHÔNG đụng**: `runtime.py`, `safety.py`, `handoff.py`, `evaluation_v2.py`, router/precedence logic, safety trigger/threshold, model call budget, `agent_v2_routes.py`, frontend. Xác nhận qua `git status --short` (chỉ 4 file thay đổi + 1 file migration mới).

---

## 9. Tests

```text
tests/test_retrieval_sql.py                 8 passed, 1 pre-existing failed (không liên quan)
tests/test_agent_v2_medical_grounding.py    28 passed
Full agent_v2-scoped suite (-k agent_v2 or orchestrator or retrieval or grounding):
    952 passed, 4 failed (3 long_term_memory + 1 word_similarity_threshold_guc,
    CẢ 4 xác nhận pre-existing -- xem §11), 3 skipped
Migration cycle: upgrade -> downgrade -> upgrade -> no-op: CLEAN
ruff check (4 file thay đổi + 1 file mới): All checks passed
```

**1 test pre-existing fail xác nhận KHÔNG liên quan migration 0047**: `test_word_similarity_threshold_guc_is_set_not_just_similarity_threshold` fail GIỐNG HỆT dù có/không có migration 0047 (verify bằng downgrade rồi chạy lại) — nguyên nhân thật là data-shape drift từ backfill local-only trước đó (BUILD-35), không phải build này.

---

## 10. Golden Before/After

Xem §6.1/§6.2 — 23/23 pass cả 2 lần, 0 regressed, 0 improved (đúng dự kiến, golden set không có case đi qua honest-decline path). Regression gate PASS cả 2 lần.

## 11. Judge Before/After

Xem §6.4 — cải thiện thật, đo trực tiếp trên đúng defect category: overall_score 0.35→0.45, relevance 0.1→0.2, flag `irrelevant_prompt_assumption` bị loại bỏ.

## 12. Latency/Token/Cost Before/After

- Latency retrieval (Cluster A): **8.621s → 5.034s (-41.6%)** đo bằng app code thật, kết quả candidate giống hệt (50=50).
- Token/cost: Cluster A không đổi (thuần DB planner hint, không đổi tokens/model calls). Cluster B không đổi (vẫn 0 model call — decline vẫn deterministic).
- Golden run wall time: 4m30s (before) → 4m20s (after) — cải thiện nhỏ trên tổng 23 case (chỉ ~4 case RAG-shaped chạm nhánh retrieval chậm).

## 13. Regressions

**0 regression thật.** Full suite: 11 failed/1735 passed (nhánh build) vs 11 failed/1733 passed (worktree `origin/main` sạch, chạy tuần tự không song song theo đúng bài học BUILD-35) — **byte-for-byte giống hệt danh sách 11 lỗi**, `1735-1733=2` khớp chính xác 2 test mới thêm (retrieval_sql). Golden: 0 regressed/23 unchanged. Critical categories (ACUTE_DANGER/POSSIBLE_OVERDOSE/SCHEDULE_*/MULTI_TURN_CONTEXT/AUTH_ISOLATION) đều PASS cả 2 lần, không đổi.

## 14. Known Limitations

1. Cluster A vẫn còn ~3-5s latency retrieval SAU fix (giảm từ 6-12s, không về 0) — đây là chi phí THẬT của GIN "recheck" (pg_trgm GIN là lossy index, luôn cần recheck) trên số dòng candidate còn lại, không thể giảm thêm mà không đổi threshold/ngưỡng (một thay đổi KẾT QUẢ tìm kiếm thật, ngoài phạm vi build "chỉ sửa planner hint" này).
2. Cluster B không loại bỏ hoàn toàn flag `unhelpful_refusal` — vẫn là 1 honest decline, chỉ liên quan hơn. Giải quyết triệt để cần mở rộng corpus (quyết định dữ liệu/phạm vi sản phẩm), ngoài scope.
3. ISSUE-03 (DRUG_INFORMATION đôi khi 0 tool call) chưa đủ evidence (2 sample) — không sửa, ghi follow-up.
4. Golden set không có case nào đi qua honest-decline path của GENERAL_MEDICAL_INFORMATION — Cluster B's cải thiện chỉ đo được qua Judge trực tiếp (§6.4), không qua golden pass/fail.

## 15. Follow-up Candidates

- ISSUE-03: audit riêng tại sao Main Model đôi khi không gọi tool cho DRUG_INFORMATION — cần nhiều sample thật hơn trước khi root-cause.
- Cân nhắc mở rộng corpus RAG với nội dung giáo dục y tế chung (không chỉ thông tin thuốc) — quyết định sản phẩm, cần thảo luận riêng.
- Cluster A: nếu latency 3-5s còn lại vẫn là vấn đề, cân nhắc giảm `CANDIDATE_POOL_SIZE`/top_k hoặc đổi threshold — nhưng đây là thay đổi KẾT QUẢ, cần đánh giá qua Golden RAG subset trước, không tự ý đổi.
- Đóng ticket `BN00028` trên production (vận hành, không phải code) — bug đã sửa từ BUILD-29F.

---

## 16. Release Gate

```text
BUILD-38: PASS

QUALITY AUDIT: PASS
ISSUE TAXONOMY: PASS
PRIORITIZATION: PASS
BASELINE CAPTURED: PASS

ROOT CAUSE CONFIRMED: PASS        (EXPLAIN ANALYZE thật cho Cluster A,
                                    Judge score thật cho Cluster B)
FIX IS SYSTEMIC: PASS
NO PHRASE-BY-PHRASE PATCHING: PASS

GOLDEN IMPROVED/UNCHANGED: PASS   (23/23 UNCHANGED, 0 regressed)
CRITICAL REGRESSION: PASS         (0 critical category regressed)
SAFETY ZERO-TOLERANCE: PASS       (không đụng safety.py/runtime.py/handoff.py)
AUTH ISOLATION: PASS              (GOLD-AUTH-001 vẫn pass)
MULTI-TURN: PASS                  (GOLD-MULTI-001 vẫn pass)

JUDGE SIGNAL: PASS                (overall +0.10, relevance +0.10, 1 flag loại bỏ)
TICKET EVIDENCE: PASS             (1 ticket thật dùng làm evidence ban đầu,
                                    xác nhận đã lỗi thời, không phải false claim)
SAFETY SIGNAL: N/A                (không có safety signal mới liên quan 2 cluster này)

LATENCY REGRESSION: PASS          (cải thiện -41.6%, không regress)
TOKEN REGRESSION: PASS            (không đổi)
COST REGRESSION: PASS             (không đổi)

FULL TEST SUITE: PASS             (11 failed/1735 passed, byte-identical
                                    pre-existing failures + 2 test mới)
RUNTIME REGRESSION: PASS          (0 file runtime/safety/router bị đụng)

READY FOR PR: YES
```

---

## 17. Branch / PR

Branch: `build-38-quality-improvement-loop`, tách từ `origin/main` (`195ed2c`, sau khi xác nhận PR #118/#119 đã merge).
Chưa deploy — theo đúng nguyên tắc chương trình (PR → review → merge → deploy, không tự deploy từ feature branch).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
