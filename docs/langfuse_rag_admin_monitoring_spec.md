# Langfuse RAG Monitoring & Admin Dashboard — Implementation Specification

> Tài liệu triển khai cho coding agent / engineering team xây hệ thống theo dõi chất lượng RAG chatbot trong Admin.
>
> **Use case:** chatbot trong ứng dụng nhắc thuốc / medication assistant.
>
> **Mục tiêu:** Admin phải trả lời được nhanh 4 câu hỏi:
>
> 1. RAG có đang xuống chất lượng không?
> 2. Vấn đề nằm ở Retrieval, Generation, Knowledge Base hay System?
> 3. Query / conversation / document nào gây ra vấn đề?
> 4. Version / component nào gây regression và cần xử lý gì?

---

## 1. Phạm vi và nguyên tắc kiến trúc

### 1.1. Vai trò của Langfuse

Dùng Langfuse làm **LLM observability + evaluation backend**, bao gồm:

- Trace toàn bộ RAG pipeline.
- Lưu observation cho retrieval, reranking, LLM generation, tool calls.
- Lưu model, prompt, token, latency, cost.
- Lưu evaluation scores.
- Lưu dataset / golden test set và experiment results.
- Chạy online evaluation bằng LLM-as-a-Judge hoặc code evaluator.
- Hỗ trợ human annotation / annotation queue.
- Cung cấp Metrics API / Scores API / Observations API cho Admin backend.

Không dùng Langfuse như database nghiệp vụ chính của app.

### 1.2. Vai trò của Admin App

Admin App là **operational monitoring UI** của sản phẩm.

Admin phải ưu tiên:

- Health overview.
- Detection của regression / incident.
- Phân tích Retrieval vs Generation.
- Drill-down vào trace cụ thể.
- So sánh version.
- Xem query/document bị lỗi nhiều nhất.
- Theo dõi alert và trạng thái xử lý.

Không cần clone toàn bộ giao diện Langfuse vào Admin.

### 1.3. Kiến trúc đề xuất

```text
User / Mobile App
       |
       v
Chat API / Agent Service
       |
       +------------------------------+
       |                              |
       v                              v
RAG Pipeline                    Product Database
       |                              |
       |                              +-- conversations
       |                              +-- feedback
       |                              +-- incidents
       |                              +-- app metadata
       |
       v
OpenTelemetry / Langfuse SDK
       |
       v
Langfuse
  |-- traces / observations
  |-- scores
  |-- datasets
  |-- experiments
  |-- model usage / cost
       |
       +-----------------------+
                               |
                               v
                     Admin Monitoring Backend
                      |-- Metrics API v2
                      |-- Scores API
                      |-- Observations API v2
                      |-- Product DB
                               |
                               v
                       Admin Dashboard UI
```

### 1.4. Vendor abstraction

Instrumentation nên dựa trên **OpenTelemetry semantics** càng nhiều càng tốt.

Không để business logic gọi Langfuse trực tiếp ở mọi nơi.

Nên có một lớp:

```text
TelemetryService
  traceRagRequest()
  traceRetriever()
  traceReranker()
  traceGeneration()
  recordScore()
  recordError()
```

Mục tiêu: có thể đổi hoặc bổ sung backend observability trong tương lai mà không sửa core RAG pipeline.

---

# 2. Khái niệm Langfuse cần dùng

Langfuse v4 tổ chức dữ liệu theo:

```text
Session
  -> Trace
      -> Observation
          -> child Observation
```

## 2.1. Session

Một **session** tương ứng một conversation/thread của user.

Ví dụ:

```text
session_id = chat_thread_01JXYZ...
```

Nhiều lượt hỏi đáp trong cùng một conversation dùng chung `session_id`.

## 2.2. Trace

Một **trace** tương ứng một interaction end-to-end:

```text
User message
   -> query processing
   -> retrieval
   -> reranking
   -> prompt construction
   -> LLM generation
   -> guardrail
   -> final response
```

Một user message => một trace.

## 2.3. Observation

Observation là từng bước của pipeline.

Dùng các type phù hợp:

- `span`: generic processing.
- `retriever`: vector / DB retrieval.
- `generation`: LLM call.
- `tool`: external tool/API call.
- `agent`: agent decision loop nếu có.
- `event`: event tức thời.

## 2.4. Score

Mọi đánh giá chất lượng phải chuẩn hóa thành **Score**.

Ví dụ:

```text
faithfulness = 0.93
answer_relevance = 0.88
hallucination = false
safety_medication = pass
user_feedback = 1
```

Score có thể được tạo bằng:

- deterministic code evaluator;
- LLM-as-a-Judge;
- RAG evaluation pipeline;
- user feedback;
- human annotation.

---

# 3. Chuẩn trace bắt buộc

## 3.1. Trace structure

Coding agent phải tạo trace gần giống cấu trúc sau:

```text
rag.chat                          [root]
|
+-- query.normalize              [span]
|
+-- query.rewrite                [generation/span] optional
|
+-- query.embedding              [span]
|
+-- retrieval.vector_search      [retriever]
|     input: normalized query
|     output: top-N chunks + similarity scores
|
+-- retrieval.rerank             [span/generation]
|     input: retrieved chunks
|     output: reordered top-K chunks + scores
|
+-- context.build                [span]
|     output: final context passed to LLM
|
+-- generation.answer            [generation]
|     input: final prompt/messages
|     output: raw model response
|
+-- safety.validate              [span]
|
+-- response.finalize            [span]
      output: final response shown to user
```

Nếu pipeline không có query rewrite / reranker thì bỏ observation đó, không tạo fake span.

## 3.2. Naming contract

Tên observation là API contract của monitoring system.

**Không đặt tên động** như:

```text
retrieval_user_123
llm_gpt_5_request_942
```

Dùng tên ổn định:

```text
rag.chat
query.normalize
query.rewrite
query.embedding
retrieval.vector_search
retrieval.rerank
context.build
generation.answer
safety.validate
response.finalize
```

Model/version đặt trong fields/metadata, không nhét vào observation name.

---

# 4. Metadata contract

Mọi trace production phải có metadata đủ để phân tích regression.

## 4.1. Trace-level attributes bắt buộc

```json
{
  "environment": "production",
  "session_id": "opaque-session-id",
  "user_id": "hashed-or-internal-id",
  "release": "backend-2.8.1",
  "tags": ["rag", "medication-chat"],
  "metadata": {
    "app_version": "4.12.0",
    "platform": "ios",
    "language": "vi",
    "feature": "medication_chat",
    "experiment_variant": "control",
    "request_id": "req_xxx"
  }
}
```

## 4.2. RAG component metadata bắt buộc

```json
{
  "prompt_version": "medication-answer-v14",
  "model": "provider/model-name",
  "embedding_model": "embedding-model-v3",
  "embedding_dimension": 1536,
  "retriever_version": "hybrid-v2",
  "reranker_version": "reranker-v3",
  "index_version": "med-kb-2026-08-20",
  "kb_version": "2026-08-20.1",
  "chunking_version": "chunker-v4"
}
```

### Rule

Nếu sau này quality score giảm, Admin phải có thể group/filter theo tất cả version trên.

---

# 5. Retrieval observation schema

`retrieval.vector_search` phải lưu đủ dữ liệu để debug ranking.

## 5.1. Input

```json
{
  "query": "normalized retrieval query",
  "filters": {
    "locale": "vi",
    "document_status": "active"
  },
  "top_n": 30
}
```

## 5.2. Output

Không log full document nếu chứa dữ liệu nhạy cảm không cần thiết.

Schema đề xuất:

```json
{
  "results": [
    {
      "document_id": "drug_123",
      "chunk_id": "drug_123_chunk_04",
      "rank": 1,
      "score": 0.873,
      "source_type": "medication_kb",
      "document_version": "2026-08-01",
      "content_preview": "redacted/limited text..."
    }
  ]
}
```

## 5.3. Reranker output

```json
{
  "results": [
    {
      "chunk_id": "drug_123_chunk_04",
      "retrieval_rank": 4,
      "rerank_rank": 1,
      "retrieval_score": 0.71,
      "rerank_score": 0.94
    }
  ]
}
```

---

# 6. Metric taxonomy

Admin metrics chia thành 5 nhóm:

1. Retrieval Quality
2. Generation Quality
3. End-to-End RAG Quality
4. Knowledge / Embedding Health
5. System / Operational Health

Không tạo một `overall_quality_score` duy nhất làm nguồn sự thật. Nếu cần overall score cho overview, nó chỉ là derived indicator và luôn phải drill-down được về component metrics.

---

# 7. Retrieval Quality Metrics

## 7.1. HitRate@K — MUST

### Ý nghĩa

Có ít nhất một relevant document/chunk xuất hiện trong top K hay không.

```text
HitRate@K = queries có >=1 relevant item trong top K / total queries
```

### Khuyến nghị

Theo dõi ít nhất:

- HitRate@1
- HitRate@5
- HitRate@10

### Nơi chạy

**Offline / golden dataset** vì cần relevance ground truth.

### Alert gợi ý

```text
HitRate@10 giảm > 5 percentage points so với baseline
```

---

## 7.2. Recall@K — MUST

Đo phần trăm relevant items được lấy ra trong top K.

```text
Recall@K = relevant retrieved @ K / total relevant items
```

Quan trọng khi một answer cần nhiều pieces of evidence.

---

## 7.3. Precision@K — SHOULD

```text
Precision@K = relevant retrieved @ K / K
```

Cho biết context có nhiều noise hay không.

---

## 7.4. MRR@K — MUST

Mean Reciprocal Rank ưu tiên relevant result xuất hiện càng sớm càng tốt.

```text
RR = 1 / rank_of_first_relevant_result
MRR = mean(RR)
```

Theo dõi MRR@10.

---

## 7.5. NDCG@K — MUST

Dùng khi relevance có nhiều mức, ví dụ:

```text
3 = authoritative/direct answer
2 = strongly relevant
1 = partially relevant
0 = irrelevant
```

NDCG đo chất lượng ranking có xét vị trí và graded relevance.

Theo dõi NDCG@10.

---

## 7.6. MAP@K — OPTIONAL / ADVANCED

Dùng nếu query thường có nhiều relevant documents và muốn đánh giá toàn bộ ranked list.

Không cần ưu tiên trong MVP nếu đã có Recall, MRR và NDCG.

---

## 7.7. Context Precision — MUST

Đánh giá các retrieved context/chunks có thực sự hữu ích cho việc trả lời hay không và relevant chunks có được xếp cao không.

Dùng cho production sampling hoặc offline evaluation.

### Target

```text
>= 0.80 good
0.65–0.80 warning
< 0.65 investigate
```

Threshold phải được calibrate trên dữ liệu thật, không hard-code vĩnh viễn.

---

## 7.8. Context Recall — MUST

Đánh giá retrieved context có chứa đủ thông tin cần thiết để trả lời câu hỏi hay không.

Một retriever có precision cao nhưng recall thấp vẫn gây answer incomplete/hallucination.

---

## 7.9. Retrieval confidence — MUST (production operational metric)

Track:

- top-1 similarity;
- top-K mean similarity;
- gap giữa rank 1 và rank 2;
- percent query có top-1 < threshold;
- percent query không có result.

Ví dụ:

```text
low_retrieval_confidence_rate =
count(top1_score < calibrated_threshold) / total queries
```

Threshold phải xác định theo từng embedding/index setup.

---

## 7.10. Duplicate / redundant context rate — SHOULD

Đo số chunk top-K trùng nội dung hoặc quá tương đồng.

```text
redundant_context_rate = redundant chunks / retrieved chunks
```

Dùng để phát hiện chunking/index problem.

---

# 8. Generation Quality Metrics

## 8.1. Faithfulness / Groundedness — CRITICAL

### Câu hỏi metric trả lời

> Những factual claims trong câu trả lời có được support bởi retrieved context hay không?

Đây là metric production quan trọng nhất cho RAG.

### Score

Chuẩn hóa numeric 0..1.

```text
1.0 = tất cả claims được support
0.0 = claims quan trọng không được support
```

### Production

Dùng LLM-as-a-Judge trên sample traffic.

### Medical use case

Không dùng LLM judge làm guardrail duy nhất cho dosage / contraindication / interaction. Các rule có structured ground truth phải có deterministic evaluator.

---

## 8.2. Answer Relevance — CRITICAL

Đo câu trả lời có trực tiếp giải quyết câu hỏi user hay không.

Một answer có thể faithfulness cao nhưng relevance thấp.

Track riêng với faithfulness.

---

## 8.3. Answer Correctness — MUST trên golden dataset

So generated answer với expected answer / reference facts.

Nên kết hợp:

- deterministic assertions;
- semantic LLM judge;
- domain-specific rules.

Không chỉ dùng string match.

---

## 8.4. Hallucination Rate — CRITICAL

Boolean/categorical score:

```text
hallucination = true | false
```

Dashboard:

```text
hallucination_rate = hallucinated responses / evaluated responses
```

Nên có severity:

```text
none
minor
material
safety_critical
```

---

## 8.5. Completeness — SHOULD

Đánh giá answer có bỏ sót phần quan trọng của câu hỏi/context hay không.

Đặc biệt hữu ích cho multi-part query.

---

## 8.6. Exact Match — LIMITED USE

Dùng cho output có canonical answer rõ ràng:

- yes/no;
- drug code;
- intent label;
- structured field;
- extraction task.

Không dùng Exact Match làm primary metric cho conversational answer.

---

## 8.7. ROUGE / BLEU — SECONDARY OFFLINE ONLY

Có thể giữ để compare benchmark lịch sử nhưng không dùng làm primary production quality metric.

Lý do: semantic answer đúng có thể có lexical overlap thấp.

---

# 9. End-to-End RAG Metrics

## 9.1. Task Success Rate — MUST

Định nghĩa cụ thể theo sản phẩm.

Ví dụ chatbot medication:

```text
SUCCESS nếu:
- trả lời đúng intent;
- factual claims được grounded;
- không vi phạm safety policy;
- không cần user hỏi lại do answer ambiguous.
```

Có thể derive từ nhiều score hoặc human label.

---

## 9.2. Citation Correctness — MUST nếu UI có citations

Mỗi citation phải support claim gắn với citation đó.

```text
citation_correctness = supported citations / citations checked
```

---

## 9.3. Citation Completeness / Coverage — SHOULD

Các factual claim quan trọng có citation hay không.

---

## 9.4. Abstention Accuracy — CRITICAL cho medication/health domain

RAG tốt phải biết khi nào **không đủ dữ liệu để trả lời**.

Track:

- abstention precision;
- abstention recall;
- unsafe answer despite insufficient evidence rate.

### Confusion matrix

```text
                    Should answer   Should abstain
Bot answers             TP              unsafe FP
Bot abstains            FN              TN
```

Đặc biệt alert nếu:

```text
should_abstain = true
AND bot_answered = true
AND medical_claim_present = true
```

---

## 9.5. User disagreement / correction rate — SHOULD

Detect các message tiếp theo như:

- "không đúng"
- "ý tôi không phải vậy"
- "bạn trả lời sai"
- correction từ user

Có thể dùng LLM classifier trên next user turn.

---

## 9.6. Re-ask / confusion rate — SHOULD

Nếu user hỏi lại cùng intent trong thời gian ngắn, đánh dấu possible failure.

```text
same_intent_within_2_turns = true
```

Đây là implicit product-quality signal rất hữu ích.

---

# 10. Medical / Medication Safety Metrics

Đây là layer riêng, không gộp vào general hallucination.

## 10.1. Safety evaluators bắt buộc

Tối thiểu:

```text
medication_dosage_consistency
medication_frequency_consistency
medication_timing_consistency
contraindication_claim_supported
drug_interaction_claim_supported
pregnancy_warning_supported
allergy_warning_supported
emergency_escalation_correct
unsupported_medical_advice
insufficient_evidence_handling
```

## 10.2. Deterministic rule ưu tiên

Nếu structured source-of-truth có:

```json
{
  "prescribed_frequency": "2/day"
}
```

và chatbot output structured extraction là:

```json
{
  "recommended_frequency": "3/day"
}
```

thì:

```text
medication_frequency_consistency = FAIL
```

Không cần LLM judge cho case deterministic này.

## 10.3. Critical safety rate

```text
critical_safety_failure_rate =
critical safety failures / evaluated medication responses
```

Admin phải thấy metric này ở top-level dashboard.

Critical failure phải tạo incident/alert ngay, không chờ aggregate daily report.

---

# 11. Knowledge Base / Embedding Health Metrics

## 11.1. Embedding drift

Không chỉ hiển thị một con số drift duy nhất.

Theo dõi:

- query embedding distribution drift;
- document embedding distribution drift;
- query-document similarity distribution drift.

Chọn statistical distance phù hợp với implementation, ví dụ PSI / Wasserstein / centroid distance / domain-specific monitoring.

Drift chỉ là signal điều tra, không tự động đồng nghĩa quality giảm.

## 11.2. Top-K similarity distribution — MUST

Track theo thời gian:

```text
p50 top1 similarity
p10 top1 similarity
average top5 similarity
% top1 below threshold
```

## 11.3. Index freshness — MUST

```text
now - newest successful index build time
```

Display:

```text
Last successful KB sync: 43 min ago
Index version: med-kb-2026-08-20
```

## 11.4. Stale document ratio — SHOULD

```text
stale_docs / indexed_docs
```

Staleness definition phải theo business policy.

## 11.5. Index coverage — SHOULD

```text
indexed_active_documents / active_source_documents
```

## 11.6. Failed ingestion / indexing rate — MUST

Track document ingestion failures riêng với RAG runtime errors.

---

# 12. System / Operational Metrics

## 12.1. End-to-end latency — MUST

Track:

- P50
- P95
- P99

Không chỉ average.

## 12.2. Component latency — MUST

Track riêng:

```text
query normalization
query rewrite
embedding
vector search
reranking
context build
LLM time-to-first-token
LLM generation
safety validation
end-to-end
```

Admin phải drill-down được component nào tạo ra P95 regression.

## 12.3. TTFT — SHOULD

Time to First Token quan trọng với perceived latency của streaming chatbot.

## 12.4. Error Rate — MUST

```text
error_rate = failed traces / total traces
```

Phân loại:

```text
provider_error
timeout
rate_limit
vector_db_error
reranker_error
invalid_output
safety_block
internal_error
```

## 12.5. Timeout Rate — MUST

Theo dõi riêng vì timeout có thể không giống generic error.

## 12.6. Token usage — MUST

Track:

- input tokens/query;
- output tokens/query;
- cached tokens nếu provider hỗ trợ;
- context token ratio.

## 12.7. Cost — MUST

Track:

```text
cost/query
cost/conversation
cost/1k successful answers
```

Breakdown theo:

```text
generation
query rewrite
reranker LLM nếu có
evaluators
embedding (nếu tính được)
```

Lưu ý evaluator cost phải tách khỏi serving cost.

## 12.8. Throughput / volume — MUST

Track request count theo:

- minute/hour/day;
- feature;
- language;
- app version;
- model;
- release.

---

# 13. Offline vs Online Evaluation Strategy

## 13.1. Offline / pre-deployment

Dùng **golden dataset + Langfuse Experiments**.

Dataset item nên có:

```json
{
  "input": {
    "query": "...",
    "user_context": {}
  },
  "expected_output": {
    "answer_facts": [],
    "should_abstain": false
  },
  "metadata": {
    "relevant_chunk_ids": [],
    "relevance_grades": {},
    "category": "dosage",
    "language": "vi",
    "risk_level": "high"
  }
}
```

Offline metrics:

```text
HitRate@K
Recall@K
Precision@K
MRR@K
NDCG@K
MAP@K optional
Answer Correctness
Faithfulness
Answer Relevance
Hallucination
Abstention precision/recall
Safety deterministic checks
```

### Deployment gate example

Không deploy nếu bất kỳ condition nào xảy ra:

```text
NDCG@10 drops > 3%
Faithfulness drops > 3%
Critical safety failures > 0
Abstention recall below approved threshold
P95 latency regression > 15%
Cost/query regression > 20% without approved exception
```

Các threshold trên là ví dụ khởi đầu; phải calibrate bằng historical data và risk appetite.

---

## 13.2. Online / production

Không cần chạy evaluator đắt tiền trên 100% traffic.

### Tier A — 100% traffic

Cheap / deterministic:

```text
latency
errors
tokens
cost
retrieval scores
no-result
low confidence
structured safety checks
user feedback
```

### Tier B — sampled traffic

LLM-as-a-Judge:

```text
faithfulness
answer relevance
context relevance / precision
hallucination
completeness
```

Start sampling ví dụ 5–10%, sau đó điều chỉnh theo cost và traffic.

### Tier C — targeted 100%

Các cohort rủi ro cao có thể evaluate toàn bộ:

```text
medication dosage questions
contraindication questions
drug interaction questions
low retrieval confidence
new prompt/model rollout
new index version
negative feedback traces
```

---

# 14. LLM-as-a-Judge implementation

Langfuse evaluator nên attach score vào observation thích hợp.

## 14.1. Faithfulness evaluator

Target:

```text
generation.answer
```

Variables:

```text
query   <- trace/root input
context <- context.build output hoặc reranker output
answer  <- generation.answer output
```

Output:

```json
{
  "score": 0.0,
  "reason": "..."
}
```

Normalize score 0..1.

## 14.2. Answer relevance evaluator

Inputs:

```text
query
answer
```

Không cần ground truth.

## 14.3. Hallucination evaluator

Inputs:

```text
context
answer
```

Output nên là categorical:

```text
none
minor
material
safety_critical
```

Có thể derive boolean `hallucination=true` từ categorical score cho alerting.

## 14.4. Judge calibration

Trước khi tin evaluator:

1. Human label một tập representative examples.
2. Chạy judge trên cùng tập.
3. Đo agreement / precision / recall / F1 tùy label.
4. Điều chỉnh rubric.
5. Không dùng cùng một judge chưa calibrate làm nguồn duy nhất cho high-risk medical safety.

---

# 15. Admin Dashboard Information Architecture

## 15.1. Page 1 — RAG Health Overview

### Global filters

```text
Time range
Environment
Release
Model
Prompt version
Embedding model
Retriever version
Reranker version
Index version
KB version
Language
Platform
App version
Risk category
```

### KPI cards

```text
RAG Quality Score (derived, optional)
Faithfulness
Answer Relevance
Context Precision
Context Recall
Hallucination Rate
Critical Safety Failure Rate
P95 Latency
Error Rate
Cost / Query
Low Retrieval Confidence Rate
```

### Required charts

1. Quality score trend by time.
2. Retrieval metrics trend.
3. Generation metrics trend.
4. P50/P95/P99 latency trend.
5. Cost/query trend.
6. Hallucination/safety trend.
7. Error rate by component.
8. Top failing categories.

### Health status

Use status derived from configured thresholds:

```text
Healthy
Warning
Critical
Unknown / insufficient sample
```

Do not display green when sample size is too small.

---

## 15.2. Page 2 — Retrieval Monitoring

Cards:

```text
HitRate@10 (offline latest benchmark)
MRR@10
NDCG@10
Context Precision
Context Recall
Low Confidence Rate
No Result Rate
```

Charts:

```text
Top-1 similarity distribution
Top-K similarity trend
Context precision over time
Context recall over time
Retrieval latency P95
```

Tables:

### Worst queries

Columns:

```text
query
count
avg top1 score
context precision
context recall
answer faithfulness
last seen
```

### Problem documents

```text
document_id
retrieval_count
avg rank
low-quality trace count
citation failure count
last indexed
```

---

## 15.3. Page 3 — Generation Monitoring

Cards:

```text
Faithfulness
Answer Relevance
Answer Correctness (offline)
Hallucination Rate
Completeness
Abstention Accuracy
```

Breakdowns:

```text
by model
by prompt version
by release
by language
by query category
by retrieval confidence bucket
```

Admin phải có thể phát hiện pattern kiểu:

```text
prompt v14 + Vietnamese + low retrieval confidence
=> hallucination 8.1%
```

---

## 15.4. Page 4 — Safety Monitoring

Top priority page cho medication app.

Cards:

```text
Critical safety failures
Dosage consistency failures
Interaction unsupported claims
Contraindication unsupported claims
Unsafe answer when should abstain
Emergency escalation failures
```

Table:

```text
severity
failure type
trace id
query category
model
prompt version
index version
timestamp
status
```

Critical row click => Trace detail.

---

## 15.5. Page 5 — Knowledge / Index Health

Cards:

```text
Current KB version
Current index version
Last successful sync
Index coverage
Stale doc rate
Failed ingestion count
Embedding drift indicator
```

Charts:

```text
Top1 similarity distribution over time
Query embedding drift
Document embedding drift
Indexing failures
Document freshness
```

---

## 15.6. Page 6 — System / Cost

Cards:

```text
Request volume
P50/P95/P99
TTFT
Error rate
Timeout rate
Tokens/query
Cost/query
Daily cost
```

Breakdown latency waterfall:

```text
embedding
retrieval
reranking
LLM
safety
other
```

Breakdown cost:

```text
serving LLM
embedding
reranker
online evaluation
```

---

## 15.7. Page 7 — Trace Explorer

Table columns:

```text
timestamp
trace_id
session_id
query preview
final answer preview
status
latency
cost
faithfulness
answer relevance
hallucination
safety
retrieval confidence
model
prompt version
index version
```

Filters:

```text
failed only
low faithfulness
hallucinated only
safety failures
negative feedback
low retrieval confidence
high latency
high cost
version filters
```

---

# 16. Trace Detail UX

Trace detail phải reconstruct được toàn bộ request.

```text
TRACE rag_98123

User query
  "..."

Timeline
  query.normalize              12 ms
  query.embedding              88 ms
  retrieval.vector_search     142 ms
  retrieval.rerank            310 ms
  context.build                18 ms
  generation.answer          1.72 s
  safety.validate              64 ms

Retrieved chunks
  #1 chunk_82  similarity .86  rerank .94
  #2 chunk_19  similarity .81  rerank .90
  #3 chunk_33  similarity .79  rerank .72

Final response
  "..."

Scores
  Context Precision      0.83
  Context Recall         0.71
  Faithfulness           0.52  WARNING
  Answer Relevance       0.91
  Hallucination          material
  Medication Safety      PASS

Versions
  model             ...
  prompt            v14
  embedding         v3
  retriever         hybrid-v2
  reranker          v3
  index             med-kb-2026-08-20
  backend release   2.8.1
```

### Root-cause helper

Có thể derive heuristic root cause:

```text
Context Recall low + Faithfulness low
=> likely retrieval insufficiency + generation issue

Context Precision low + Relevance low
=> likely noisy retrieval

Context strong + Faithfulness low
=> likely generation hallucination

All quality strong + latency bad
=> system performance issue
```

Hiển thị là **Likely cause**, không khẳng định certainty nếu chỉ là heuristic.

---

# 17. Admin Backend + Langfuse API strategy

## 17.1. Aggregate dashboard

Dùng **Metrics API v2** cho:

- count / volume;
- latency aggregates;
- cost;
- token usage;
- score aggregates;
- group-by model / trace attributes / time;
- filters theo metadata/version.

Không fetch hàng chục nghìn raw observations rồi aggregate trong Admin backend nếu Metrics API đáp ứng được.

## 17.2. Score drill-down

Dùng **Scores API** khi cần score rows / evaluator details.

## 17.3. Trace / observation drill-down

Dùng **Observations API v2** để lấy row-level spans/generations/retrieval observations.

## 17.4. Caching

Admin dashboard không cần hit Langfuse cho mọi UI render.

Khuyến nghị:

```text
Overview aggregates: cache 30–120 seconds
Historical daily metrics: cache longer
Trace detail: fetch on demand
Critical incident: near real-time
```

---

# 18. Derived metrics storage

Các IR metric như MRR/NDCG thường được tính trong offline evaluation job.

Sau khi tính:

1. Lưu experiment result vào Langfuse.
2. Có thể ingest score tương ứng.
3. Lưu benchmark summary vào Admin analytics DB nếu cần query nhanh.

Ví dụ:

```json
{
  "experiment_id": "rag-benchmark-2026-08-20",
  "release": "2.8.1",
  "metrics": {
    "hit_rate_10": 0.942,
    "mrr_10": 0.846,
    "ndcg_10": 0.872,
    "faithfulness": 0.931
  }
}
```

Không cố tính MRR production nếu không có relevance labels đáng tin cậy.

---

# 19. Alerting specification

Alert phải actionable và có link đến affected traces.

## 19.1. Critical alerts

Ví dụ:

```text
Critical medical safety failure > 0
Critical hallucination detected in high-risk category
Error rate > 5% for 5 min
P95 > approved threshold for 10 min
No-result rate > 10% for 10 min
Index sync failed
Index freshness > SLA
```

## 19.2. Regression alerts

Dùng relative baseline + minimum sample size.

Ví dụ:

```text
Faithfulness drops >= 8% vs trailing 7-day baseline
AND evaluated_samples >= 100
```

Không alert chỉ dựa trên 3 sample.

## 19.3. Alert payload

```json
{
  "metric": "faithfulness",
  "severity": "high",
  "current": 0.78,
  "baseline": 0.91,
  "sample_size": 430,
  "started_at": "...",
  "top_correlations": {
    "prompt_version": "v14",
    "language": "vi",
    "index_version": "..."
  },
  "affected_trace_ids": []
}
```

---

# 20. Privacy & sensitive health data

Medication/health conversation có thể chứa dữ liệu nhạy cảm.

## 20.1. Default policy

- Không log PII không cần thiết.
- `user_id` dùng opaque/internal/hash identifier.
- Redact phone/email/name nếu không cần debugging.
- Không gửi toàn bộ medical profile vào metadata.
- Chỉ log context cần thiết để debug RAG.
- Có retention policy cho raw trace content.
- Phân quyền Admin trace viewer.

## 20.2. Masking

Ưu tiên client-side masking trước khi telemetry rời application boundary.

Nếu self-hosted và license/architecture phù hợp, server-side ingestion masking có thể dùng như lớp bổ sung.

Client-side masking vẫn là lớp chính nếu dữ liệu tuyệt đối không được truyền ra ngoài boundary trước khi redact.

## 20.3. Audit

Admin access đến raw conversation/trace nên audit được:

```text
admin_user
trace viewed
time
reason optional
```

---

# 21. Golden Dataset Design

Golden dataset không được chỉ chứa easy queries.

## 21.1. Categories

Tối thiểu:

```text
medication schedule
missed dose
before/after meal
dosage clarification
drug interaction
contraindication
allergy
pregnancy
side effect
emergency symptoms
out-of-scope medical advice
insufficient KB evidence
ambiguous medication name
Vietnamese typo / slang
multi-turn context
```

## 21.2. Risk stratification

Mỗi case:

```text
low
medium
high
critical
```

Critical safety cases phải pass 100% deterministic gates trước deploy.

## 21.3. Production feedback loop

```text
Production bad trace
       |
       v
Human review
       |
       v
Add to golden dataset
       |
       v
Future experiment / CI regression test
```

Đây là vòng lặp bắt buộc để dataset ngày càng đại diện cho failure thực tế.

---

# 22. Implementation phases

## Phase 1 — Instrumentation

Deliverables:

- Langfuse/OpenTelemetry setup.
- Stable trace naming contract.
- Session + trace propagation.
- Retriever, reranker, generation spans.
- Model/token/cost capture.
- Version metadata.
- PII masking.

Acceptance criteria:

- 99%+ successful chat interactions tạo được trace.
- Một trace hiển thị full parent-child timeline.
- Có retrieved chunk IDs + scores.
- Có model/prompt/index versions.
- Có session replay cho multi-turn conversation.

---

## Phase 2 — System Monitoring

Deliverables:

- request volume;
- P50/P95/P99;
- component latency;
- error/timeout;
- tokens;
- cost.

Acceptance criteria:

Admin có thể tìm nguyên nhân của latency regression đến component-level.

---

## Phase 3 — Retrieval Evaluation

Deliverables:

- golden relevance labels;
- HitRate@K;
- Recall/Precision@K;
- MRR@10;
- NDCG@10;
- Context Precision;
- Context Recall;
- low-confidence production metric.

Acceptance criteria:

Có dashboard compare metrics giữa ít nhất 2 retriever/index versions.

---

## Phase 4 — Generation Evaluation

Deliverables:

- faithfulness;
- answer relevance;
- answer correctness offline;
- hallucination;
- completeness;
- LLM judge sampling.

Acceptance criteria:

Admin có thể filter traces `faithfulness < threshold` và xem full context + answer.

---

## Phase 5 — Medical Safety

Deliverables:

- deterministic medication checks;
- abstention evaluation;
- safety severity classification;
- critical alerting.

Acceptance criteria:

Critical safety failure được surface thành incident cùng trace evidence.

---

## Phase 6 — Regression & CI/CD

Deliverables:

- Langfuse dataset experiments;
- release comparison;
- automated deployment gates;
- regression alerting.

Acceptance criteria:

Pull request/release thay đổi prompt/model/retriever có benchmark report trước production deployment.

---

# 23. MVP metric set

Nếu cần build nhanh, **không làm tất cả metric ngay**.

MVP bắt buộc:

## Retrieval

```text
HitRate@10          offline
MRR@10              offline
NDCG@10             offline
Context Precision   sampled prod + offline
Context Recall      sampled prod + offline
Low Confidence Rate production 100%
No Result Rate      production 100%
```

## Generation

```text
Faithfulness        sampled production
Answer Relevance    sampled production
Answer Correctness  offline
Hallucination Rate  sampled production
```

## Safety

```text
Abstention accuracy
Medication deterministic consistency
Critical Safety Failure Rate
```

## System

```text
P50/P95/P99 latency
component latency
error rate
timeout rate
tokens/query
cost/query
```

## Knowledge

```text
index freshness
index version
index coverage
top1 similarity distribution
```

## Tracing

```text
query -> embedding -> retrieval -> rerank -> context -> LLM -> safety -> response
```

---

# 24. Recommended score names

Tên score phải ổn định, snake_case và version evaluator riêng trong metadata/config.

```text
retrieval_context_precision
retrieval_context_recall
retrieval_low_confidence
answer_faithfulness
answer_relevance
answer_correctness
answer_completeness
hallucination_severity
should_abstain
abstention_correct
citation_correctness
citation_completeness
medication_dosage_consistency
medication_frequency_consistency
medication_timing_consistency
medical_claim_supported
critical_safety_failure
user_helpful_feedback
user_disagreement
```

Không đổi score name mỗi lần sửa prompt evaluator. Version evaluator thay vì đổi metric identity.

---

# 25. Recommended Admin API endpoints

Ví dụ contract nội bộ:

```text
GET /admin/rag/health
GET /admin/rag/retrieval
GET /admin/rag/generation
GET /admin/rag/safety
GET /admin/rag/knowledge
GET /admin/rag/system
GET /admin/rag/traces
GET /admin/rag/traces/:traceId
GET /admin/rag/experiments
GET /admin/rag/versions/compare
GET /admin/rag/incidents
```

Common query params:

```text
from
to
environment
release
model
prompt_version
embedding_model
retriever_version
reranker_version
index_version
language
category
```

Backend tự map sang Langfuse Metrics/Scores/Observations APIs.

Không expose Langfuse secret key ra browser.

---

# 26. Version comparison view

Admin phải support compare:

```text
A: prompt v13
B: prompt v14
```

hoặc:

```text
A: index 2026-08-10
B: index 2026-08-20
```

Table:

| Metric | A | B | Delta | Status |
|---|---:|---:|---:|---|
| NDCG@10 | 0.87 | 0.82 | -5.7% | regression |
| Faithfulness | 0.93 | 0.90 | -3.2% | warning |
| Answer relevance | 0.91 | 0.92 | +1.1% | improved |
| P95 | 3.8 s | 4.6 s | +21% | regression |
| Cost/query | $0.012 | $0.010 | -17% | improved |

Admin phải xem cả **quality, latency và cost trade-off**, không optimize một chiều.

---

# 27. Sample root-cause matrix

| Signal | Possible problem | Next action |
|---|---|---|
| HitRate low | retriever/index | inspect relevance labels, filters, index |
| HitRate good, MRR low | ranking | tune retriever/reranker |
| Context Precision low | noisy context | reranking/chunk/filter tuning |
| Context Recall low | missing evidence | increase coverage/query rewrite/index |
| Context good, Faithfulness low | generator hallucination | prompt/model/guardrail |
| Faithfulness good, Relevance low | answer follows context but misses intent | intent/prompt issue |
| Low confidence rising | KB/query distribution shift | inspect embedding/index/query cohorts |
| P95 high, retrieval normal | LLM/system | inspect generation/provider |
| P95 high, reranker high | reranker bottleneck | optimize reranker |
| Safety failure after new prompt | prompt regression | rollback + experiment |
| Quality drops only on new index | KB/index regression | compare affected documents |

---

# 28. Definition of Done

Hệ thống monitoring được xem là đủ dùng khi một Admin không cần đọc raw server log mà vẫn có thể:

1. Nhìn overview và biết health status.
2. Nhận biết retrieval hay generation đang regression.
3. Filter theo release/model/prompt/index.
4. Mở một failed trace.
5. Xem retrieved chunks và ranking scores.
6. Xem prompt/model response và evaluator scores.
7. Xác định likely root cause.
8. Xem các traces cùng pattern.
9. So sánh trước/sau một version change.
10. Với lỗi safety-critical, thấy incident và evidence ngay.

---

# 29. Instructions for the coding agent

Coding agent triển khai theo các rule sau:

1. **Đọc Langfuse docs hiện tại trước khi coding.** API/SDK versions thay đổi; không copy API cũ từ blog/tutorial.
2. Ưu tiên SDK/OpenTelemetry version được Langfuse docs hiện tại khuyến nghị.
3. Dùng stable observation names trong spec này.
4. Không log PII/health data mặc định.
5. Không tính aggregate bằng raw observation scan nếu Metrics API có thể làm trực tiếp.
6. Không chạy LLM judge 100% traffic trừ high-risk cohort có lý do rõ ràng.
7. Mọi evaluator phải có documented rubric và version.
8. LLM judge phải được calibrate bằng human labels trước khi dùng làm KPI quan trọng.
9. Deterministic rule luôn ưu tiên cho structured medical facts.
10. Mọi release/prompt/model/index change phải trace được qua metadata.
11. Mọi metric dashboard phải có sample size hoặc denominator.
12. Không alert khi sample size không đủ.
13. Threshold phải configurable, không hard-code trong UI.
14. Metric card phải drill-down được tới cohort hoặc trace phù hợp.
15. Critical safety failure phải có đường dẫn trực tiếp đến trace evidence.
16. Golden dataset phải được bổ sung từ production failures theo vòng lặp liên tục.

---

# 30. Langfuse API usage map

| Requirement | Langfuse capability |
|---|---|
| Trace pipeline | Observability / OpenTelemetry SDK |
| Multi-turn chat | Sessions |
| LLM calls | Generation observations |
| Retriever | Retriever observations |
| Quality result | Scores |
| Production LLM judge | Observation-level evaluators |
| Deterministic quality | Code evaluator / Scores API/SDK |
| Human review | Annotation / Annotation Queues |
| Golden dataset | Datasets |
| Regression testing | Experiments |
| Aggregate admin KPI | Metrics API v2 |
| Row-level drill-down | Observations API v2 |
| Evaluation rows | Scores API |
| Langfuse native charts | Custom Dashboards |

---

# 31. References — read before implementation

Langfuse documentation changes over time. The coding agent should fetch the current version of these pages before implementation.

- Langfuse Observability Overview: https://langfuse.com/docs/observability/overview
- Langfuse Observability Data Model: https://langfuse.com/docs/observability/data-model
- Langfuse Trace Best Practices: https://langfuse.com/docs/observability/best-practices
- Langfuse Observation Types: https://langfuse.com/docs/observability/features/observation-types
- Langfuse Sessions: https://langfuse.com/docs/observability/features/sessions
- Langfuse Metadata: https://langfuse.com/docs/observability/features/metadata
- Langfuse Token & Cost Tracking: https://langfuse.com/docs/observability/features/token-and-cost-tracking
- Langfuse Evaluation Overview: https://langfuse.com/docs/evaluation/overview
- Langfuse Evaluation Core Concepts: https://langfuse.com/docs/evaluation/core-concepts
- Langfuse Scores: https://langfuse.com/docs/evaluation/scores/overview
- Langfuse LLM-as-a-Judge: https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge
- Langfuse Metrics API: https://langfuse.com/docs/metrics/features/metrics-api
- Langfuse Custom Dashboards: https://langfuse.com/docs/metrics/features/custom-dashboards
- Langfuse Observations API: https://langfuse.com/docs/api-and-data-platform/features/observations-api
- Langfuse Scores API: https://langfuse.com/docs/api-and-data-platform/features/scores-api
- Langfuse Data Platform Overview: https://langfuse.com/docs/api-and-data-platform/overview
- Langfuse Data Masking: https://langfuse.com/self-hosting/security/data-masking
- Langfuse docs for coding agents: https://langfuse.com/agents
- Ragas documentation: https://docs.ragas.io/

### Agent-friendly Langfuse docs access

Langfuse currently exposes agent-friendly documentation. Before writing integration code, the coding agent can use:

```bash
curl -s https://langfuse.com/llms.txt
```

and fetch markdown versions of docs pages by appending `.md`, for example:

```bash
curl -s https://langfuse.com/docs/observability/overview.md
```

Do this to verify SDK/API examples against the latest Langfuse release rather than relying only on this static specification.

---

# 32. Final architecture principle

The monitoring system should optimize for **debuggability and actionability**, not for maximum metric count.

The desired diagnostic chain is:

```text
Is quality degrading?
        |
        v
Retrieval / Generation / Knowledge / System / Safety?
        |
        v
Which cohort/version?
        |
        v
Which traces?
        |
        v
Which pipeline step failed?
        |
        v
What change should engineering make?
```

If a metric cannot help answer one of those questions, it is likely secondary and should not occupy prime Admin dashboard space.
