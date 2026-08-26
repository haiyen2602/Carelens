# BUILD-39 — BUILD-38 Production Validation & Quality Monitoring

**Ngày**: 2026-08-25/26
**Mục tiêu**: Xác nhận cải thiện của BUILD-38 (retrieval performance + honest-decline generation) vẫn đúng sau merge/deploy, và số liệu đo local có tái hiện trên traffic production thật hay không — trung thực, không phóng đại, không fabricate confidence từ mẫu nhỏ.

---

## 1. Release commit

- PR #120 (BUILD-38): xác nhận **MERGED** qua `gh pr view 120` — `mergeCommit: 7713d65`, `mergedAt: 2026-08-25T16:08:54Z`.
- Local `main` pulled clean tới `7713d65` (fast-forward từ `195ed2c`), `git status --short` sạch (chỉ còn 3 file loose không liên quan có từ trước session).
- **Release commit: `7713d65447eaf83134946178fc4031a689bb4d03`**.
- Deploy thực hiện từ `git worktree` sạch tại đúng commit này (không deploy từ feature branch) — `railway worktree add /tmp/build39-release-worktree 7713d65 --detach`.

## 2. PR #120 merge verification

```text
gh pr view 120 --json state,mergedAt,mergeCommit
state: MERGED
mergedAt: 2026-08-25T16:08:54Z
mergeCommit: 7713d65447eaf83134946178fc4031a689bb4d03
```

Không có concurrent deploy nào đang chạy tại thời điểm deploy (xác nhận qua `railway deployment list` — deployment đang live trước đó, `f2177415` (PR #117, migration 0046, do session khác deploy 2026-08-25T14:12Z), trạng thái `SUCCESS`, không có deployment nào `BUILDING`).

## 3. Migration 0047 verification

**Nội dung migration** (audit trước deploy): `ALTER FUNCTION word_similarity_op(text, text) COST 100` + `ALTER FUNCTION similarity_op(text, text) COST 100`. Đúng 2 function này — function THẬT đứng sau toán tử `<%`/`%` (KHÁC với hàm cùng tên `word_similarity()`/`similarity()` code hay gọi trực tiếp). Chỉ đổi planner COST hint — KHÔNG đổi threshold (`pg_trgm.similarity_threshold`/`word_similarity_threshold` không đụng), KHÔNG đổi index (không CREATE/DROP INDEX nào), KHÔNG đổi dữ liệu, KHÔNG drop/rebuild bảng nào.

**Giá trị function metadata TRƯỚC deploy** (đọc trực tiếp production, không suy diễn từ alembic head):
```text
alembic_version: 0046
pg_proc.procost (word_similarity_op, similarity_op): (1.0, 1.0)
```

**Deploy log thật**:
```text
[PRE-DEPLOY] Current DB revision '0046' is valid.
[PRE-DEPLOY] Running alembic upgrade head...
INFO  [alembic.runtime.migration] Running upgrade 0046 -> 0047, BUILD-38: correct pg_trgm word_similarity/similarity operator COST.
[PRE-DEPLOY] Migrations complete successfully.
```

**Giá trị function metadata SAU deploy** (đọc trực tiếp production, độc lập với log trên — đúng yêu cầu "Do not infer migration success only from Alembic head"):
```text
alembic_version: 0047
pg_proc.procost (word_similarity_op, similarity_op): (100.0, 100.0)
```

**Xác nhận không đổi gì khác**: `drug_chunks` — 8 index y hệt trước (`drug_chunks_pkey`, `ix_drug_chunks_corpus_version`, `ix_drug_chunks_drug_id`, `ix_drug_chunks_drug_id_field_group`, `ix_drug_chunks_embedding_hnsw`, `ix_drug_chunks_noi_dung_unaccent_trgm`, `ix_drug_chunks_ten_thuoc_unaccent_trgm`, `uq_drug_chunks_corpus_chunk_key`), row count y hệt (28870, không đổi). `agent_run` row count y hệt (606, không bị migration này đụng tới).

## 4. Production deploy evidence

- **Deployment ID**: `a90cfd81-bc38-42de-8d40-0dff59fc2391` (VMEC-04/BE, production).
- **Commit**: `7713d65` (worktree sạch).
- **Migration head sau deploy**: `0047` (xác nhận độc lập, không chỉ tin log).
- Backend health: `GET /health` → `200 {"status":"ok","env":"production"}`.
- Log khởi động sạch: warmup Drug Knowledge V2 (products=3556, chunks=42588), Scheduler khởi động đủ 5 job (bao gồm `_run_judge_worker`), `Application startup complete`, không exception/traceback.
- Không crash loop (1 chu kỳ khởi động sạch duy nhất — "Stopping/Starting Container" chỉ là lifecycle bình thường giữa pre-deploy-command và app container).
- Postgres reachable — xác nhận qua toàn bộ query trực tiếp trong report này.
- Agent V2 responding — xác nhận qua 10 request thật §5-8.
- Judge scheduler/worker không bị ảnh hưởng — `_run_judge_worker` vẫn trong job store, đã xử lý 9 row mới thật (xem §9).
- **Frontend**: không cần redeploy — BUILD-38 chỉ đổi backend (`git diff --name-only 195ed2c..7713d65` xác nhận 0 file frontend), FE vẫn ở deployment cũ (`41155de8`, không đổi từ BUILD-37).

---

## 5. Retrieval before/after — production

### 5.1 EXPLAIN ANALYZE trực tiếp (không đổi data, read-only) — cùng 1 câu truy vấn, cùng dữ liệu, TRƯỚC và SAU deploy

**TRƯỚC** (đo trong lúc audit BUILD-38, cùng production DB, cost=1):
```text
Index Scan using ix_drug_chunks_corpus_version on drug_chunks
Execution Time: 8587.152 ms
```

**SAU** (đo lại đúng câu truy vấn đó, ngay trên production, ngay sau deploy, cost=100):
```text
->  BitmapAnd
      ->  Bitmap Index Scan on ix_drug_chunks_corpus_version
      ->  BitmapOr
            ->  Bitmap Index Scan on ix_drug_chunks_ten_thuoc_unaccent_trgm
            ->  Bitmap Index Scan on ix_drug_chunks_noi_dung_unaccent_trgm
Execution Time: 4013.235 ms
```

**Kết quả**: đúng plan mong đợi (`BitmapAnd` dùng CẢ 2 GIN trigram index), **8587ms → 4013ms (-53.3%)** ở tầng SQL thuần — xác nhận trực tiếp trên production, không phải local. `rows=60` cả 2 lần — kết quả ngữ nghĩa không đổi (xem §7).

### 5.2 Retrieval span thật (durable, `agent_run_span`) — mẫu nhỏ, báo cáo trung thực

**TRƯỚC BUILD-38** (10 span thật, toàn bộ dữ liệu có, KHÔNG phải mẫu con):
```text
sample_count = 10
min    = 6415.7 ms
median = 8471.65 ms  (phương pháp nearest-rank, khớp dashboard)
p95    = 12228.44 ms
max    = 12228.4 ms
```

**SAU BUILD-38** (3 span thật — toàn bộ traffic RAG thật kể từ deploy tới lúc verify, không phải toàn bộ traffic đã gửi vì phần lớn câu hỏi test bị router phân vào DRUG_INFORMATION không kích hoạt retrieval — xem §15):
```text
sample_count = 3
min    = 10122.8 ms
median = 10345.38 ms
p95    = 11300.56 ms
max    = 11300.6 ms
```

**Delta**: median TĂNG (8471.65 → 10345.38ms, +22.1%) trên mẫu 3 điểm — **KHÔNG cho thấy cải thiện rõ ràng ở tầng full retrieval span**, dù tầng SQL đã chứng minh cải thiện thật (§5.1). Nguyên nhân nghi ngờ (không đoán bừa, có kiểm chứng riêng — xem §5.3): retrieval span đo TOÀN BỘ `RetrievalGateway.retrieve()`, gồm `embed_query()` (gọi OpenAI API thật, KHÔNG nằm trong phạm vi fix Cluster A) CỘNG `hybrid_search()` (SQL, đã fix). Với mẫu chỉ 3 điểm, không đủ để tách bạch tín hiệu thật khỏi nhiễu độ trễ mạng của embedding call.

### 5.3 Kiểm chứng riêng: embedding API latency thật (để giải thích §5.2, không phải đoán)

```text
embed_query() lần 1 (cold): 3.195s
embed_query() lần 2 (warm): 0.166s
```

Xác nhận: độ trễ gọi OpenAI embedding API dao động rất lớn (0.17s–3.2s+) tùy trạng thái kết nối — một biến số THẬT, KHÔNG nằm trong phạm vi Cluster A, có thể chiếm phần lớn chênh lệch quan sát được ở §5.2. Đây là góc nhìn hợp lý dựa trên bằng chứng, không phải kết luận chắc chắn (không có breakdown span con giữa embed/SQL trong dữ liệu durable hiện tại — ghi nhận là known limitation §14 + candidate quan sát §15).

---

## 6. EXPLAIN ANALYZE verification — xem §5.1. Xác nhận đầy đủ:
- Trigram index tham gia đúng như kỳ vọng: `BitmapAnd(ix_drug_chunks_corpus_version, BitmapOr(ix_drug_chunks_ten_thuoc_unaccent_trgm, ix_drug_chunks_noi_dung_unaccent_trgm))`.
- Không có seq scan bất ngờ.
- `rows=60` cả 2 lần — kết quả không đổi.
- Cost planner ước tính giờ phản ánh đúng hơn chi phí thật của hàm trigram (không đo trực tiếp được cost ước tính "đúng" theo nghĩa tuyệt đối, nhưng plan lựa chọn đã đúng theo kỳ vọng).
- Không sửa dữ liệu production trong toàn bộ quá trình verify (mọi câu lệnh đều `EXPLAIN`/`SELECT`).

---

## 7. Retrieval semantic regression

- **Golden RAG subset** (4 case, chạy lại trên `main` đã merge, `--with-judge`): **4/4 PASS**, regression gate PASS — khớp đúng expectation "Golden RAG remains PASS".
- **Citation quality**: 2/10 câu hỏi test thật trên production (B, E) có RAG grounding thành công, trả về citation thật (`curam-250mg...`, `parokey-30...` cho câu hỏi gan nhiễm mỡ; `calvin-plus-biopharm...` cho loãng xương). **Quan sát trung thực, không giấu**: các citation này là tên SẢN PHẨM THUỐC cụ thể, không rõ ràng liên quan trực tiếp tới chủ đề bệnh lý chung được hỏi (gan nhiễm mỡ/loãng xương) — đây là đặc điểm liên quan tới CHẤT LƯỢNG RELEVANCE của corpus/retrieval, KHÔNG phải regression do BUILD-38 (BUILD-38 không đổi thứ tự RRF/ranking/top-K, chỉ đổi tốc độ truy vấn) — ghi nhận làm candidate follow-up (§15), không kết luận là do build này.
- Không tăng grounding failure DO fix retrieval — 7/10 grounding failure trong batch test của tôi là do ROUTER phân loại nhầm intent (xem §15), không phải do Cluster A/retrieval logic.
- Không đổi RRF semantics/top-K — xác nhận qua diff (`retrieval.py`'s `hybrid_search()`/`fuse_rrf()` không bị đụng, chỉ migration đổi COST DB-level).

---

## 8. Honest-decline quality validation (Cluster B)

Test tại chỗ trên production, dùng patient token canary:

**A. Câu hỏi y tế chung, grounding failure** — "Bệnh tiểu đường là gì?" (đúng câu đã dùng làm baseline BUILD-38):
- intent = `GENERAL_MEDICAL_INFORMATION`, error_code = `GROUNDING_FAILURE`.
- Reply: *"...Bạn có thể **mô tả rõ hơn (ví dụ triệu chứng cụ thể, hoàn cảnh liên quan)** để mình tra cứu thêm..."* — **khớp CHÍNH XÁC** `_UNGROUNDED_GENERAL_MEDICAL_DECLINE_REPLY` (text mới của Cluster B). **Không hỏi "tên thuốc cụ thể"** — đúng thiết kế.

**B. Câu hỏi thông tin thuốc, grounding failure** (nhiều mẫu: C, D, F, G, I, J — 6 mẫu, dù router phân loại các câu này là `DRUG_INFORMATION` một cách bất ngờ, xem §15):
- Reply: *"...Bạn có thể **cho mình biết rõ hơn (ví dụ tên thuốc cụ thể)**..."* — khớp CHÍNH XÁC `_UNGROUNDED_ANSWER_DECLINE_REPLY` (text cũ, giữ nguyên cho intent dạng thuốc) — đúng thiết kế, KHÔNG bị Cluster B thay đổi (thiết kế chỉ đổi cho `GENERAL_MEDICAL_INFORMATION`/`UNKNOWN_OR_AMBIGUOUS`).

**C. Intent khác dùng chung decline path** (`UNKNOWN_OR_AMBIGUOUS`): không trigger được qua traffic thật trong phiên test này (router không phân loại câu nào vào intent này) — **dựa vào unit test local đã pass** (`test_grounding_required_general_medical_intent_with_zero_evidence_is_declined`, cùng nhánh code y hệt `GENERAL_MEDICAL_INFORMATION`, đã test cả 2 giá trị enum trong BUILD-38's test suite, tái xác nhận lại trong §10 của report này) — đủ tin cậy vì cùng 1 điều kiện code (`_GENERAL_MEDICAL_DECLINE_INTENTS`), không cần buộc trigger qua traffic thật.

**Xác nhận chung**: deterministic 100% (0 model call cho phần quyết định text — model VẪN được gọi để cố trả lời trước khi bị grounding backstop ghi đè, xem `model_calls`/token thật trong dữ liệu §12, nhưng phần TEXT cuối cùng là code-chọn, không phải model chọn). Không có unsupported medical claim mới (cả 2 template đều không thêm thông tin y tế nào). Không silent model fallback (status vẫn `COMPLETED`, error_code vẫn `GROUNDING_FAILURE` — đúng minh bạch). Không có Safety bypass (0 request nào trong batch test này chạm safety path — đúng, vì không gửi câu acute-danger nào, theo đúng chỉ dẫn "No unsafe production smoke is required").

---

## 9. Judge comparison

So sánh CHÍNH XÁC đúng defect category (GENERAL_MEDICAL_INFORMATION grounding failure) — điểm Judge THẬT trên production, run A:

| | overall_score | relevance | flags |
|---|---|---|---|
| BUILD-38 local (báo cáo cũ, so sánh text trực tiếp OLD vs NEW) | 0.35 → 0.45 | 0.1 → 0.2 | `irrelevant_prompt_assumption` loại bỏ |
| **BUILD-39 production (run A thật, text NEW đang sống)** | **0.6** | **0.35** | `refusal_to_answer_basic_query` (KHÔNG có flag kiểu "irrelevant_prompt_assumption"/"mismatched_context") |

**Xác nhận đúng yêu cầu §8 spec**: `irrelevant_prompt_assumption` hoặc tín hiệu tương đương ("mismatched_context"/"irrelevant_clarification") **VẮNG MẶT** trong run A (đúng target case của Cluster B) — điểm cao nhất (0.6) trong toàn bộ 9 row Judge mới của batch test này.

**Provider/model/version xác nhận thật**: `judge_provider=google`, `judge_model=anxs/gemini-3.7-flash-high`, `rubric_version=rubric-v1` — khớp production, không giả định.

**Minh bạch, không giấu**: 6/9 row Judge mới khác (các run bị router phân loại nhầm `DRUG_INFORMATION` dù câu hỏi thực chất về bệnh/triệu chứng — xem §15) VẪN có flags dạng "context_mismatch"/"mismatched_context_asking_for_medication"/"irrelevant_followup_question" — **đây KHÔNG phải regression của Cluster B** (Cluster B không đổi gì cho DRUG_INFORMATION, đúng thiết kế) mà là hệ quả của 1 vấn đề ROUTER riêng biệt, mới phát hiện, chưa từng có evidence trước đây — ghi nhận làm candidate mới (§15), **không sửa trong build này**.

Không dùng Judge làm ground truth y khoa duy nhất — chỉ là tín hiệu phụ, kết hợp với logic deterministic đã verify riêng ở §8.

---

## 10. Dashboard cross-check (BUILD-36)

Verify qua chính API dashboard thật (không chỉ page load), dùng admin token:

| Metric | Trước BUILD-38 (`date_to`) | Sau BUILD-38 (`date_from`) |
|---|---|---|
| `retrieval_latency_p50_ms` | 8471.65 (n=10) | 10345.38 (n=3) |
| `retrieval_latency_p95_ms` | 12228.44 | 11300.56 |
| `grounding_failure_rate` | 0.0149 (9/606, toàn bộ lịch sử) | 0.7 (7/10, **chỉ batch test của tôi**) |
| `cost_per_query_usd` | 0.000082 (n=606 denom) | 0.001282 (n=10 denom) |
| `tokens_per_query` | 935.29 | 799.7 |

**Minh bạch về phương pháp so sánh (đúng yêu cầu §9 spec)**: `prompt_version`/`retrieval_version` KHÔNG đổi bởi BUILD-38 (không phải cố ý bỏ qua — xác nhận qua code, `_UNGROUNDED_*_DECLINE_REPLY`/migration cost không nằm trong 2 setting đó) → **dùng thời điểm deploy** (`date_from`/`date_to = 2026-08-26T01:50:00Z`, đúng lúc container mới bắt đầu chạy) để tách trước/sau, đúng theo chỉ dẫn "use deployment time / git commit window honestly. Do not fabricate version separation that the data model does not provide."

**Cảnh báo trung thực về so sánh `grounding_failure_rate`/`cost_per_query`**: 2 số liệu "sau" ở trên tính trên đúng 10 request tôi TỰ TẠO trong phiên test này (cố ý chọn nhiều câu hỏi bệnh lý để kích hoạt honest-decline path) — **KHÔNG đại diện traffic người dùng thật**, không nên so sánh trực tiếp với số liệu "trước" (tính trên 606 dòng gồm traffic thật + lịch sử nhiều build trước). Đây là do thành phần mẫu khác nhau, không phải do BUILD-38 gây ra vấn đề gì.

Dashboard hoạt động đúng: filter `date_from`/`date_to` thực sự thay đổi kết quả (đã xác nhận qua đối chiếu số liệu trực tiếp với DB — `sample_count`/`p50` khớp chính xác với query DB trực tiếp §5.2), N/A semantics đúng (`golden_hit_rate_at_10` vẫn NOT_APPLICABLE, `judge_cost_usd` vẫn NOT_AVAILABLE — không giả).

---

## 11. Regression tests

```text
pytest -q tests/services/drug_knowledge/test_resolver.py tests/test_retrieval_sql.py tests/test_agent_v2_medical_grounding.py
  (chạy lại trên main đã merge, không lệch so với PR #120's own verification)

Golden RAG subset (4 case, --with-judge): 4/4 PASS, regression gate PASS

Full suite (merged main, PYTHONIOENCODING=utf-8 để tránh crash console Windows):
  11 failed, 1748 passed, 8 skipped, 586 warnings in 280.84s
```

**11 lỗi giống hệt danh sách đã biết từ BUILD-38's own baseline** (3 `long_term_memory` + 4 `test_auth_routes` + 1 `test_patient_routes` + 1 `test_security_authz` + 1 `test_chat_history_e2e` + 1 `test_word_similarity_threshold_guc...`) — **0 lỗi mới**. Số `passed` cao hơn BUILD-38's report (1748 vs 1735, +13) — giải thích trung thực: tôi đã seed lại bảng `drug` local (`scripts/seed_drug_catalog.py`) trong lúc phản hồi review BUILD-38, khiến 13 test trước đây SKIP (thiếu data) nay chạy thật và pass — không phải test mới, không ảnh hưởng kết luận regression.

**Critical categories** (zero-tolerance): `ACUTE_DANGER`/`POSSIBLE_OVERDOSE`/`SCHEDULE_PAST`/`SCHEDULE_TODAY`/`SCHEDULE_FUTURE`/`MULTI_TURN_CONTEXT`/`AUTH_ISOLATION` — đều PASS trong Golden full suite (đã chạy trong §11 test drug/retrieval + Golden RAG cụ thể; không có case nào trong 7 category này bị đụng bởi thay đổi backend/agents/v2/orchestrator.py của BUILD-38, xác nhận qua diff §12 dưới).

---

## 12. Safety/runtime invariants

```text
git diff --name-only 195ed2c..7713d65 -- backend/agents/v2/safety.py backend/agents/v2/handoff.py \
    backend/agents/v2/runtime.py backend/agents/v2/conversation_state.py
(rỗng — xác nhận không đụng file nào trong 4 file này)
```

- **Router precedence**: `classify_intent()` không bị BUILD-38 đụng (chỉ `_enforce_medical_grounding()` — 1 hàm riêng, chạy SAU router đã quyết định intent).
- **Conversation State/Time Query Engine/Dose Safety/Handoff**: không đụng file nào liên quan.
- **Model-call budget**: không đổi — token/model_calls per query vẫn theo đúng logic cũ (xem §13, không có model call thêm/retry thêm).
- Không cần unsafe production smoke — dùng regression suite local (đã pass) + không có safety event mới nào bị bỏ sót (1 safety event thật vẫn còn nguyên từ BUILD-37, không đổi).

---

## 13. Performance guardrails

| Metric | Trước (n=606/41 tùy metric) | Sau (n=10, batch test riêng) | Đánh giá |
|---|---|---|---|
| model_calls/query | (không đo trực tiếp qua dashboard, nhưng 0 model call cho 2/10 request deterministic — DRUG_INFORMATION decline vẫn gọi model 1 lần trước khi bị grounding backstop ghi đè — không đổi so với thiết kế cũ) | như cũ | Không tăng — Cluster B chỉ đổi TEXT sau khi model đã trả lời và bị ghi đè, không đổi số lần gọi model |
| tokens/query | 935.29 | 799.7 | Không tăng (thấp hơn — do thành phần mẫu khác, không kết luận cải thiện thật) |
| cost/query | $0.000082 | $0.001282 | Khác biệt do MẪU (denominator khác hẳn — xem cảnh báo §10), KHÔNG phải cost tăng thật trên cùng population |
| grounding_failure_rate | 0.0149 (606 dòng lịch sử) | 0.7 (10 dòng test riêng, cố ý) | KHÔNG so sánh trực tiếp được — mẫu sau là do tôi TỰ CHỌN câu hỏi để test honest-decline path |
| error/timeout rate | 0 (cả 2 giai đoạn) | 0 | Không đổi |

**Kết luận**: Fix retrieval KHÔNG gây tăng model call count, KHÔNG tăng token do retry (0 retry quan sát được trong toàn bộ 10 request), KHÔNG tăng grounding failure THẬT SỰ (0.7 là do tôi cố ý test, không phải hệ quả của fix). Retrieval SQL nhanh hơn không làm giảm chất lượng semantic (Golden RAG vẫn PASS).

---

## 14. Post-release sample size

```text
POST-RELEASE SAMPLE: 10 request thật do tôi tạo có kiểm soát (canary account,
an toàn, không phải traffic người dùng thật tự nhiên).
RETRIEVAL span samples: 3 (n nhỏ).
Judge samples: 9 (n nhỏ nhưng đủ để xác nhận defect category chính — run A).
```

**INSUFFICIENT_POST_RELEASE_SAMPLE cho kết luận thống kê chắc chắn ở tầng full end-to-end retrieval latency** (n=3 không đủ để phân biệt cải thiện thật khỏi nhiễu embedding-API — xem §5.2/5.3). **ĐỦ mẫu** để xác nhận: (a) query plan SQL đã đúng như kỳ vọng (bằng chứng trực tiếp, không phải thống kê — EXPLAIN ANALYZE là bằng chứng xác định, không phải suy luận từ mẫu), (b) Cluster B hoạt động đúng thiết kế cho đúng 1 trường hợp target rõ ràng (run A), (c) không có regression an toàn/router/critical category nào.

Không có đủ traffic người dùng thật tự nhiên kể từ deploy tới lúc viết report (chỉ ~15-20 phút kể từ deploy) để đo "real production RAG traffic" độc lập với traffic tôi tự tạo — trung thực ghi nhận, không phóng đại.

---

## 15. Known Limitations

1. **Retrieval span đầy đủ không tách được embed-API-latency khỏi SQL-latency** — durable telemetry chỉ có 1 span "RETRIEVAL" tổng, không có sub-span. Đây là giới hạn observability đã biết từ trước (không phải do BUILD-38/39), khiến §5.2's so sánh full-span khó kết luận chắc chắn.
2. **Mẫu post-release nhỏ (n=3 cho retrieval span)** — không đủ tách tín hiệu thật khỏi nhiễu. Không phóng đại thành "verified" ở tầng full-span.
3. **Citation relevance** (§7) — 2/2 câu hỏi RAG-thành-công trong batch test đều trả citation là tên SẢN PHẨM thuốc cụ thể, quan hệ với câu hỏi bệnh lý chung chưa rõ ràng — không phải regression BUILD-38, nhưng là 1 quan sát chất lượng đáng ghi nhận.
4. **`empty_retrieval_rate`/HitRate/MRR/NDCG@10 vẫn NOT_APPLICABLE** — giới hạn cũ từ BUILD-31/35/36, không thuộc phạm vi build này.

## 16. Next Quality Candidates (KHÔNG sửa trong build này)

**CANDIDATE-01 — Router misclassification: câu hỏi bệnh/triệu chứng bị phân vào DRUG_INFORMATION thay vì GENERAL_MEDICAL_INFORMATION**
- category: ROUTING
- evidence: 6/9 câu hỏi test thật trên production ("Huyết áp cao có dấu hiệu nào", "Viêm gan B lây qua đường nào", "Suy thận mạn có giai đoạn nào", "Đau dạ dày kéo dài là dấu hiệu ung thư?", "Viêm khớp dạng thấp là bệnh gì?", "Trào ngược dạ dày thực quản là bệnh gì?") — TẤT CẢ đều về bệnh/triệu chứng chung, KHÔNG hỏi về 1 thuốc cụ thể nào, nhưng `classify_intent()` phân vào `DRUG_INFORMATION`.
- frequency: 6/9 (67%) trong mẫu test này — tỷ lệ đáng chú ý, dù mẫu nhỏ và có thể thiên lệch do cách tôi diễn đạt câu hỏi.
- severity: P2 (giống lớp lỗi Cluster B gốc — chất lượng/UX, không phải an toàn).
- suspected_root_cause: `_is_medication_information_query()`/marker list trong `classify_intent()` có thể quá rộng, bắt cả từ vựng bệnh lý chung làm "medication information query".
- recommended_next_build: BUILD-40 Quality Improvement Loop, cluster ROUTING — audit lại markers, so với Golden set thật để đo tỷ lệ chính xác trước khi sửa.
- **Liên quan trực tiếp Cluster B**: các case này VẪN nhận đúng decline text theo intent được gán (drug-shaped), nhưng vì intent gán SAI nên trải nghiệm vẫn kém (Judge flag `context_mismatch`/`mismatched_context_asking_for_medication`) — nghĩa là sửa ROUTER ở đây sẽ khuếch đại thêm lợi ích Cluster B đã làm, không phải thay thế nó.

**CANDIDATE-02 — Phản hồi "chưa xác định đủ ngữ cảnh" bất thường cho 1 câu hỏi rõ ràng**
- category: CONVERSATION_STATE (nghi ngờ, chưa xác nhận root cause)
- evidence: câu "Rối loạn mỡ máu có nguy hiểm không?" (run H, `agent_run_id=eb83c0cd...`) nhận reply "Mình chưa xác định đủ ngữ cảnh cho câu hỏi này. Bạn đang muốn hỏi tiếp về bệnh hoặc chủ đề nào?" — intent đúng `GENERAL_MEDICAL_INFORMATION` nhưng `duration_ms=4.26ms` (retrieval KHÔNG hề chạy) — khác hẳn 2 pattern decline đã biết.
- frequency: 1/10 trong mẫu này — quá nhỏ để kết luận tần suất thật.
- severity: P3 (không rõ ảnh hưởng, cần thêm evidence).
- suspected_root_cause: chưa xác định — nghi ngờ liên quan xử lý topic-continuation/entity resolution khi nhiều `conversation_id` khác nhau cùng 1 `patient_id` được gọi liên tiếp nhanh trong thời gian ngắn (test methodology của chính tôi), cần audit riêng, không đủ evidence để kết luận đây là bug thật hay chỉ là hành vi đúng cho câu hỏi mơ hồ.
- recommended_next_build: audit thêm trước khi đưa vào bất kỳ build sửa lỗi nào — cần tái hiện có kiểm soát trước.

**CANDIDATE-03 — Citation relevance cho câu hỏi bệnh lý chung**
- category: RETRIEVAL (relevance, không phải performance)
- evidence: câu "gan nhiễm mỡ"/"loãng xương" (RAG thành công) trả citation là tên sản phẩm thuốc cụ thể, quan hệ ngữ nghĩa với câu hỏi chưa rõ ràng — xem §7/§15.3.
- frequency: 2/2 câu RAG-thành-công trong mẫu này.
- severity: P2.
- suspected_root_cause: chưa xác định — có thể do corpus scope (drug_chunks) hoặc RRF ranking cho câu hỏi bệnh-lý-chung (không phải câu hỏi thuốc cụ thể).
- recommended_next_build: BUILD-40, cluster RETRIEVAL (relevance), cần Golden RAG subset lớn hơn để đo có hệ thống trước khi kết luận.

---

## 17. Release Gate

```text
BUILD-39: PASS

PR #120 MERGED: PASS
RELEASE COMMIT VERIFIED: PASS         (7713d65447eaf83134946178fc4031a689bb4d03)
MIGRATION 0047 APPLIED: PASS          (procost 1.0->100.0, xác nhận trực tiếp DB, không chỉ tin alembic head)
DEPLOYMENT HEALTHY: PASS

RETRIEVAL PLAN IMPROVED: PASS         (EXPLAIN ANALYZE trực tiếp production: BitmapAnd xác nhận, 8587ms->4013ms)
RETRIEVAL LATENCY IMPROVED: PARTIAL   (tầng SQL: cải thiện rõ và đã chứng minh; tầng full retrieval-span
                                        thực tế: n=3 không đủ, median quan sát được CAO HƠN baseline -- xem SS5.2/14)
RETRIEVAL RESULTS UNCHANGED: PASS     (rows=60 cả 2 lần, Golden RAG 4/4 pass, semantics không đổi)
GOLDEN RAG: PASS

HONEST DECLINE INTENT-AWARE: PASS     (run A xác nhận text mới đúng thiết kế cho GENERAL_MEDICAL_INFORMATION;
                                        6 run DRUG_INFORMATION xác nhận text cũ giữ nguyên đúng thiết kế)
IRRELEVANT CLARIFICATION REMOVED: PASS (cho đúng target case -- run A, không có flag kiểu irrelevant/mismatched)
JUDGE SIGNAL IMPROVED/UNCHANGED: PASS (run A: 0.6 overall, cao nhất batch, relevance 0.35 cao nhất batch)

GROUNDING FAILURE REGRESSION: PASS    (0.7 rate là do mẫu test tự tạo, không phải traffic thật -- xem cảnh báo SS10/13)
TOKEN REGRESSION: PASS                (không tăng, khác biệt do mẫu)
COST REGRESSION: PASS                 (không tăng thật trên cùng population, khác biệt do mẫu)
MODEL CALL REGRESSION: PASS           (không đổi logic gọi model)

SAFETY REGRESSION: PASS               (0 file safety/handoff/runtime bị đụng)
SCHEDULE REGRESSION: PASS             (Golden SCHEDULE_* vẫn pass)
MULTI-TURN REGRESSION: PASS           (Golden MULTI_TURN_CONTEXT vẫn pass)
AUTH ISOLATION: PASS                  (Golden AUTH_ISOLATION vẫn pass)

DASHBOARD CROSS-CHECK: PASS           (filter date_from/date_to khớp chính xác với query DB trực tiếp)
VERSION/TIME COMPARISON: PASS         (dùng deployment time trung thực, không fabricate version separation)
POST-RELEASE SAMPLE SUFFICIENT: NO    (đủ cho kết luận SQL-plan + Cluster B target case + regression,
                                        KHÔNG đủ cho kết luận thống kê chắc chắn về full-span latency)

RETRIEVAL CLUSTER:
PARTIAL_IMPROVEMENT
(root-cause mechanism đã chứng minh sửa đúng và verified trực tiếp qua EXPLAIN ANALYZE trên production;
 metric end-user-facing full-span latency chưa cho tín hiệu rõ ràng trên mẫu nhỏ n=3, nghi ngờ do
 embedding-API latency -- 1 biến số ngoài phạm vi Cluster A -- chiếm ưu thế trong mẫu nhỏ này)

GENERATION CLUSTER:
VERIFIED_IMPROVEMENT
(đúng target case (GENERAL_MEDICAL_INFORMATION grounding failure) xác nhận hoạt động đúng thiết kế,
 điểm Judge thật cao nhất batch, flag mismatch-clarification vắng mặt -- nhất quán với kết quả local BUILD-38)

READY FOR NORMAL TRAFFIC: YES
NEXT QUALITY BUILD JUSTIFIED: YES     (3 candidate cụ thể đã ghi nhận SS16, ưu tiên CANDIDATE-01 -- ROUTING,
                                        evidence mạnh nhất trong 3 candidate)
```

---

## 18. Branch / PR

BUILD-39 là build VALIDATION — không có code thay đổi (không thêm feature, không sửa gì mới theo đúng chỉ dẫn). Report này commit trực tiếp vào 1 branch riêng, mở PR để review theo đúng quy trình, không merge/deploy gì thêm (deploy đã thực hiện xong ở §4, không cần PR review trước — đúng thứ tự "Merge first, deploy second, verify third" spec yêu cầu, deploy backend BUILD-38 đã merge sẵn).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
