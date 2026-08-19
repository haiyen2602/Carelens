# Agent Architecture V2 --- Detailed Architecture Plan

**Status:** Draft for iterative review\
**Purpose:** Architecture/planning only. Review and refine section by
section before implementation.

## 1. Context

Application Integration V2 has completed the approved local integration
boundary. The current foundation includes Canonical Drug Knowledge V2,
Doctor Prescription V2 sidecar integration, medication plans/schedules,
bounded dose occurrences, audited dose-state transitions, Safety
assessment/escalation boundaries, outbox-only notification behavior,
legacy-compatible API/DTO paths, and local E2E validation.

Agent Architecture V2 sits **above these audited application/domain
boundaries**. The Agent must not become a new source of truth for
clinical or operational data.

## 2. Primary goals

Build an extensible AI assistant that can:

1.  Understand user requests and authenticated context.
2.  Select trusted tools/data sources.
3.  Retrieve patient medication information safely.
4.  Retrieve structured Drug Knowledge V2.
5.  Use RAG for semantic/open questions.
6.  Search only approved Vinmec web domains for supplementary public
    information.
7.  Route missed/delayed-dose questions through Safety Domain.
8.  Hand off questions requiring clinical judgment to a doctor instead
    of guessing.
9.  Generate grounded answers with provenance.
10. Maintain conversation context without treating LLM memory as
    clinical truth.
11. Support future text, voice, image, and other interfaces.
12. Be observable, testable, cost-aware, and model-provider replaceable.

## 3. Core principle

``` text
LLM = understand + route + orchestrate + summarize + explain
Operational DB = truth about patient/application state
Drug Knowledge V2 = structured truth about canonical medicines
RAG = semantic supporting knowledge
Vinmec Web Search = approved public supplementary information
Safety Domain = medication-safety assessment/escalation decision
Doctor = human clinical judgment when required
```

The LLM is **not** the source of truth.

## 4. High-level architecture

``` text
                         USER
                ┌─────────┼─────────┐
              Text      Voice     Image
                └─────────┼─────────┘
                          ↓
                 INPUT ADAPTER LAYER
                          ↓
                AUTHENTICATED CONTEXT
                          ↓
              ┌───────────────────────┐
              │      AGENT CORE       │
              │ Intent / Routing      │
              │ Context Manager       │
              │ Model Gateway         │
              │ Tool Orchestrator     │
              │ Response Composer     │
              └───────────┬───────────┘
                          ↓
        ┌─────────────────┼──────────────────┐
        ↓                 ↓                  ↓
 Operational Tools   Knowledge Tools    Safety Tools
        │             Drug V2 / RAG          │
        │             Vinmec Web             │
        └─────────────────┬──────────────────┘
                          ↓
                  DOCTOR HANDOFF
                  when required
                          ↓
                 RESPONSE COMPOSER
                          ↓
                 OUTPUT ADAPTER LAYER
                    ↙             ↘
                  Text            Voice
```

## 5. Agent authority

### Agent may

-   Read authorized patient medication context through approved tools.
-   Search canonical drug information.
-   Retrieve today's/upcoming doses.
-   Explain prescriptions and schedules.
-   Execute explicitly approved dose-state actions through domain
    services.
-   Request Safety Domain assessments.
-   Retrieve supporting RAG knowledge.
-   Search approved Vinmec web sources.
-   Create doctor-review requests when clinical judgment is required.
-   Summarize verified context for doctors.
-   Explain domain/tool results in user-friendly language.

### Agent must not

-   Query/mutate application tables directly.
-   Invent medications, prescriptions, schedules, dose states, or drug
    identity.
-   Prescribe, change dosage, stop/switch treatment, or create clinical
    policy.
-   Independently decide missed-dose risk.
-   Override Safety Domain.
-   Convert `UNKNOWN`/`REQUIRE_MEDICAL_REVIEW` into reassurance.
-   Use web content to override patient-specific clinical policy.
-   Use conversation memory as proof that medication was taken.
-   Expose another patient's information.
-   Store arbitrary sensitive information as long-term memory.

## 6. Request lifecycle

``` text
User request
→ Authentication / authorization
→ Input normalization
→ Intent classification
→ Context resolution
→ Tool planning
→ Tool execution
→ Safety/policy gate when applicable
→ Doctor handoff when required
→ Grounded response generation
→ Audit / observability
→ User response
```

## 7. Routing architecture

Initial intent families:

``` text
GENERAL_CONVERSATION
DRUG_INFORMATION
PRESCRIPTION_INFORMATION
TODAY_DOSES
UPCOMING_DOSES
DOSE_STATUS
DOSE_ACTION
MISSED_DOSE
DELAYED_DOSE
SAFETY_QUESTION
GENERAL_MEDICAL_INFORMATION
DOCTOR_REVIEW
UNKNOWN_OR_AMBIGUOUS
```

### Source-of-truth matrix

  ---------------------------------------------------------------------
  Request                            Primary source
  ---------------------------------- ----------------------------------
  Patient prescription               Operational DB via tools

  Dose schedule/state                Operational DB via tools

  Structured drug fact               Drug Knowledge V2

  Open semantic drug/medical         RAG
  question                           

  Supplementary public explanation   Vinmec Web Search

  Missed/delayed-dose safety         Safety Domain

  Clinical judgment / unsafe         Doctor Handoff
  ambiguity                          

  "Thuốc lúc nãy" style reference    Conversation Context +
                                     authoritative lookup
  ---------------------------------------------------------------------

Routing principle:

``` text
Trusted structured data available? → structured tool
Semantic knowledge needed? → RAG
Supplementary public explanation needed? → Vinmec Web Search
Patient-specific safety decision? → Safety Domain
Clinical judgment / cannot resolve safely? → Doctor Handoff
```

Web search never substitutes for mandatory doctor review.

## 8. Model architecture

Models must be configurable:

``` text
AGENT_ROUTER_MODEL=
AGENT_MAIN_MODEL=
AGENT_FALLBACK_MODEL=
AGENT_SUMMARY_MODEL=
EMBEDDING_MODEL=
STT_MODEL=
TTS_MODEL=
```

### Router model

Handles intent classification, lightweight extraction,
required-context/tool hints, and structured routing output. Start by
evaluating a low-cost small model. A dedicated router may be removed if
a single Main Agent performs better end-to-end.

### Main Agent

Handles context understanding, tool planning/calling, reference
resolution, evidence consumption, and grounded response generation.
Start by evaluating a strong tool-use mini-tier model.

### Fallback model

May handle difficult **non-clinical orchestration/reasoning**. A
stronger LLM never replaces mandatory Doctor Handoff.

### Embedding model

Used only for semantic retrieval. Embeddings do not determine patient
state or safety.

## 9. Cost-aware routing

Planning scale:

``` text
1,000 users × 20 requests/day × 30 days
= 600,000 user requests/month
```

Track input/output/cached tokens, model calls, tool calls, retrieval
size, latency, and estimated cost per request/intent/user.

Requirements:

-   avoid full chat history on every request;
-   cap RAG context;
-   compact tool results;
-   support prompt caching where available;
-   support complexity-based model routing;
-   budget alerts;
-   do not permanently hard-code models before evaluation.

## 10. Tool architecture

Agent calls application/domain tools, never ORM/database code.

Every tool contract defines:

``` text
name
purpose
authorized roles
input/output schema
read/write classification
idempotency
timeout
error taxonomy
audit fields
PII classification
clinical-risk classification
confirmation requirement
```

### Drug tools

``` text
search_drug
get_drug_info
get_drug_ingredients
get_drug_indications
get_drug_interaction_info
```

### Prescription tools

``` text
get_active_prescriptions
get_prescription_detail
get_prescription_history
```

Prescription modification is not initially exposed.

### Dose/Schedule tools

``` text
get_today_doses
get_upcoming_doses
get_dose_status
```

### Candidate Dose Action tools

``` text
mark_dose_taken
mark_dose_delayed
mark_dose_skipped
```

Exact write/confirmation policy must be approved first.

### Safety tools

``` text
assess_missed_dose
assess_delayed_dose
get_safety_decision
get_safety_history
```

These wrap Safety Domain. Risk rules must not be recreated in prompts.

### Doctor Handoff tools

``` text
request_doctor_review
get_handoff_status
get_doctor_response
```

### Tool gateway controls

-   authenticated actor;
-   authorization/patient ownership;
-   correlation ID;
-   timeout/rate limit;
-   audit logging;
-   normalized errors;
-   explicit allowlist of callable tools.

## 11. Vinmec Web Search

Implement a dedicated tool such as:

``` text
search_vinmec_web(query)
```

It must enforce an explicit allowlist of approved Vinmec
domains/subdomains. The exact list is a design decision.

Flow:

``` text
Agent determines supplementary public information is useful
→ search_vinmec_web
→ domain allowlist
→ approved results
→ sanitize/extract
→ title + source + content/excerpt + timestamp
→ Agent answers with provenance
```

Allowed use:

-   general medical explanations;
-   supplementary current/public education;
-   user-facing sources.

Not allowed:

-   overriding Operational DB;
-   overriding canonical Drug Identity;
-   overriding Safety Domain;
-   replacing Doctor Handoff;
-   turning general articles into patient-specific treatment advice.

Treat retrieved web pages as **untrusted data**, never as Agent
instructions. Defend against prompt injection, stale pages, duplicate
results, excessive context, and lost provenance.

## 12. RAG architecture

``` text
Question
→ query normalization
→ embedding
→ retrieval
→ metadata filters
→ optional reranking
→ bounded context
→ Main Agent
```

Retrieved chunks should preserve source, section, canonical entity where
available, provenance, version/date, and chunk ID.

Prefer structured lookup for known fields. Use RAG for semantic
synthesis. Never use vector similarity alone to resolve a patient's
medicine identity.

## 13. Memory & Context

``` text
Agent Memory
├── Operational Context
├── Short-term Conversation Memory
├── Conversation Summary
└── Approved Long-term Memory
```

### Operational Context

Patient identity, active prescriptions, dose occurrences/states, and
safety assessments come from authoritative application/domain services.

### Short-term Conversation Memory

Used for conversational references and continuity. Review integration
of:

``` text
conversation
message
agent_run
agent_tool_event
```

### Conversation Summary

For long chats:

``` text
recent messages
+ compact verified summary
+ current operational context
```

Summaries must distinguish user claims, verified tool facts, and
unresolved claims.

### Long-term Memory

Not approved by default. Before implementation define allowed facts,
consent, retention, correction/deletion, provenance, sensitivity, and
retrieval rules.

Clinical events remain in authoritative operational domains, not
arbitrary LLM memory.

## 14. Agent Context envelope

Candidate:

``` text
request_id
conversation_id
message_id
actor_id
actor_role
patient_id
timezone
locale
referenced_drug_id
referenced_prescription_id
referenced_dose_occurrence_id
intent
risk_disposition
recent_context
verified_context_refs
```

Model-produced IDs must be resolved and authorized server-side.

## 15. Safety architecture

Safety is a domain boundary, not a prompt.

``` text
"Tôi quên uống thuốc sáng nay"
→ resolve patient
→ resolve relevant dose occurrence
→ get_dose_status
→ assess_missed_dose
→ Safety Domain
→ structured disposition/risk/action/provenance
→ Agent explains result
```

`UNKNOWN` or `REQUIRE_MEDICAL_REVIEW` must remain fail-closed and may
trigger Doctor Handoff.

## 16. Doctor Handoff / Human Escalation

First-class capability.

Candidate mandatory triggers:

-   Safety Domain returns `REQUIRE_MEDICAL_REVIEW`;
-   safety is `UNKNOWN`;
-   user asks to change dosage;
-   user asks whether to stop/switch medication;
-   symptoms/circumstances exceed approved Agent capability;
-   patient/drug/dose cannot be resolved safely;
-   trusted sources conflict and require clinical judgment;
-   tool pipeline cannot determine a safe answer.

Exact policy requires product/clinical review.

Flow:

``` text
Patient question
→ Agent gathers minimum necessary verified context
→ Safety/tool evaluation
→ Doctor review required
→ request_doctor_review
→ Doctor Review Domain
→ assignment
→ Doctor reads context and responds
→ response stored with provenance
→ patient receives doctor response
```

Candidate persistence (not yet an approved migration):

``` text
doctor_review_request
- id
- patient_id
- conversation_id
- source_message_id
- assigned_doctor_id
- reason_code
- priority
- risk_disposition
- patient_question
- agent_summary
- verified_context_refs
- status
- created_at
- assigned_at
- resolved_at
```

Candidate statuses:

``` text
PENDING
ASSIGNED
ANSWERED
CANCELLED
```

Doctor assignment must use an approved treating-doctor/care-team/routing
relationship. Agent must not randomly select a doctor.

## 17. Read/write action policy

Classify tools:

``` text
READ_ONLY
LOW_RISK_WRITE
SENSITIVE_WRITE
CLINICAL_WRITE
```

Initial direction:

-   lookups → READ_ONLY;
-   `mark_dose_taken` → candidate controlled write;
-   skip/delay → explicit policy review;
-   prescription modification → unavailable initially;
-   safety-policy modification → prohibited;
-   doctor-review request → controlled write.

Every write defines confirmation, authorization, idempotency key, retry
semantics, audit trail, and rollback/compensation behavior.

## 18. Confirmation policy

Avoid confirmation for harmless reads. Require stronger confirmation for
state-changing actions.

Candidate UX:

``` text
"Thuốc hôm nay của tôi?" → read directly

"Tôi đã uống viên 8h" → resolve exact occurrence
→ if unambiguous, approved write policy
→ if ambiguous, ask clarification

"Bỏ liều này đi" → confirmation/policy gate

"Đổi tôi sang 2 viên" → cannot perform → Doctor Handoff
```

## 19. Error & ambiguity taxonomy

``` text
AUTH_REQUIRED
FORBIDDEN
PATIENT_CONTEXT_MISSING
ENTITY_NOT_FOUND
ENTITY_AMBIGUOUS
DRUG_UNRESOLVED
DOSE_UNRESOLVED
INVALID_STATE_TRANSITION
SAFETY_REVIEW_REQUIRED
TOOL_TIMEOUT
TOOL_UNAVAILABLE
RAG_NO_EVIDENCE
WEB_NO_APPROVED_SOURCE
DOCTOR_HANDOFF_REQUIRED
INTERNAL_ERROR
```

Models receive structured errors, never raw stack traces.
Safety-relevant ambiguity must not be guessed.

## 20. Grounding & provenance

Track claim sources:

``` text
OPERATIONAL_DB
DRUG_KNOWLEDGE_V2
RAG
VINMEC_WEB
SAFETY_DOMAIN
DOCTOR
MODEL_GENERAL_LANGUAGE
```

Web/RAG answers should expose sources when useful. Doctor-authored
responses must remain distinguishable from AI explanations.

## 21. Prompt architecture

Avoid one giant prompt.

``` text
Base Agent Policy
+ Role/Authorization Context
+ Tool Schemas
+ Current Request Context
+ Retrieved Evidence
+ Safety Disposition
```

Do not duplicate audited clinical policy into prompts. Version prompts
and trace prompt versions.

## 22. Multimodal / Voice-ready architecture

Agent Core operates on normalized messages/events, not directly on UI
text.

``` text
Text / Voice / Image / Document
→ Input Adapter
→ normalized request
→ Agent Core
→ normalized response
→ Output Adapter
→ Text / Voice
```

Voice input:

``` text
Audio → Speech-to-Text → Agent Core
```

Voice output:

``` text
Agent response → Text-to-Speech → Audio
```

Future realtime voice can reuse the same Tool Gateway and domain
boundaries. STT/TTS/realtime models must be replaceable via
configuration. TTS must not alter clinical meaning.

## 23. Security & privacy

Required controls:

-   authentication on every request;
-   server-side patient authorization;
-   role-based tool permissions;
-   least privilege;
-   no secrets in prompts;
-   no DB credentials exposed to Agent;
-   PII minimization in model context/traces;
-   configurable retention;
-   prompt-injection defenses;
-   audit for sensitive tools;
-   no cross-patient memory leakage.

## 24. Prompt injection / untrusted content

RAG documents and web pages are data, not instructions. Retrieved
content must never be able to:

-   change system policy;
-   request secrets;
-   authorize tools;
-   change patient identity;
-   bypass Safety Domain;
-   trigger writes;
-   alter Doctor Handoff rules.

## 25. Observability

Trace:

``` text
request
→ auth/context
→ router/model
→ tool plan
→ tool calls
→ retrieval
→ safety
→ doctor handoff
→ final response
```

Suggested metadata:

``` text
request_id
conversation_id
intent
model/model_version
prompt_version
tool_name/status/latency
retrieval_source
safety_disposition
handoff_created
input/output/cached tokens
estimated_cost
total_latency
```

Do not log hidden chain-of-thought or unnecessary PII.

LangSmith can be evaluated here, but architecture should not be
vendor-locked.

## 26. Agent persistence

Review existing/foundation entities:

``` text
conversation
message
agent_run
agent_tool_event
```

Potential additions:

``` text
conversation_summary
doctor_review_request
doctor_response/review_event
agent_evaluation_result
```

Do not create migrations until persistence and retention requirements
are approved.

## 27. Evaluation architecture

Measure:

-   intent accuracy;
-   tool-selection accuracy;
-   entity resolution;
-   grounding/hallucination;
-   safety compliance;
-   Doctor Handoff accuracy;
-   authorization;
-   usefulness;
-   citation quality;
-   latency;
-   token usage/cost.

Scenario families:

``` text
drug lookup/explanation
active prescription
today/upcoming doses
multiple drugs same time
taken/missed/delayed dose
unresolved/ambiguous drug
unsafe request
dose-change/stop-medication request
reviewed/unknown safety policy
Vinmec search
RAG / no evidence
web no approved result
tool timeout / DB error
wrong-patient access
doctor handoff / doctor response
conversation-memory reference
retrieval prompt injection
```

Safety eval must verify correct domain/tool use, not just whether final
prose sounds reasonable.

## 28. Local Agent E2E

Target:

``` text
Patient message
→ correct intent
→ authorized context
→ correct tool(s)
→ correct patient/drug/dose
→ Safety Domain when required
→ Doctor Handoff when required
→ grounded response
→ conversation/tool audit persisted
```

Validate locally before production.

## 29. Feature flags

Candidate flags:

``` text
AGENT_RUNTIME_ENABLED=
AGENT_ROUTER_MODE=
AGENT_MEMORY_MODE=
AGENT_RAG_ENABLED=
AGENT_VINMEC_WEB_ENABLED=
AGENT_DOCTOR_HANDOFF_ENABLED=
AGENT_WRITE_ACTIONS_ENABLED=
AGENT_OBSERVABILITY_ENABLED=
VOICE_INPUT_ENABLED=
VOICE_OUTPUT_ENABLED=
```

## 30. Rollout strategy

``` text
OFF
→ INTERNAL_TEST
→ READ_ONLY_SHADOW
→ READ_ONLY_USER_TRAFFIC
→ CONTROLLED_WRITE_ACTIONS
→ DOCTOR_HANDOFF
→ BROADER_USER_TRAFFIC
```

Sensitive writes require their own gates.

## 31. Proposed implementation workstreams

-   **AG-1 Current Agent Audit** --- audit chatbot code, endpoints,
    prompts, models, persistence, RAG, tools, auth, legacy behavior.
-   **AG-2 Agent Boundary & Policy** --- finalize authority/prohibitions
    and clinical boundaries.
-   **AG-3 Runtime & Model Gateway** --- configurable models, structured
    output, retry/timeout, cost-aware routing foundation.
-   **AG-4 Router & Context Manager** --- intent routing, references,
    authenticated context.
-   **AG-5 Tool Gateway & Core Tools** --- typed
    Drug/Prescription/Dose/Safety tools.
-   **AG-6 Knowledge & RAG** --- structured vs semantic retrieval with
    provenance.
-   **AG-7 Vinmec Web Search** --- allowlisted web retrieval and source
    handling.
-   **AG-8 Memory** --- conversation persistence, short-term context,
    summaries, retention.
-   **AG-9 Safety & Action Policy** --- Safety routing, write
    classifications, confirmations, fail-closed behavior.
-   **AG-10 Doctor Handoff** --- review persistence, assignment,
    lifecycle, doctor response, patient delivery.
-   **AG-11 Agent Runtime Integration** --- connect Agent Core to local
    chat UI behind flags.
-   **AG-12 Observability** --- traces, model/tool metrics, cost
    accounting, evaluation hooks; evaluate LangSmith.
-   **AG-13 Evaluation & Red Team** --- datasets, automated
    Agent/safety/auth/prompt-injection tests and cost benchmarks.
-   **AG-14 Local Agent E2E** --- complete local patient-chat flow
    validation.
-   **AG-15 Closeout** --- readiness, remaining risks, next production
    gates.

## 32. Explicitly out of initial implementation scope

Unless separately approved:

-   autonomous diagnosis/prescribing;
-   autonomous dosage/treatment changes;
-   Agent-authored safety policy;
-   unrestricted internet search;
-   production notification provider;
-   production scheduler;
-   automatic production cutover;
-   Railway deployment;
-   legacy retirement;
-   realtime voice implementation;
-   image-based clinical diagnosis.

Voice-readiness belongs in architecture; voice implementation can be a
later phase.

## 33. Open design decisions

1.  Dedicated router model or Main Agent routing?
2.  Final V2 intent taxonomy?
3.  Which Agent tools may write state?
4.  Does `mark_dose_taken` require confirmation?
5.  How are ambiguous dose references resolved?
6.  Exact approved Vinmec domains/subdomains?
7.  Internal RAG vs live Vinmec-search boundary?
8.  Conversation-history window?
9.  Persist conversation summaries?
10. Is long-term memory needed in V2?
11. What may memory retain and for how long?
12. Exact mandatory Doctor Handoff triggers?
13. How is responsible doctor resolved?
14. What if no doctor is available?
15. Synchronous or asynchronous doctor response?
16. How is patient notified of doctor response?
17. Which handoff fields require DB migration?
18. Approved tone for uncertainty/safety?
19. Which model wins Vietnamese medical eval?
20. Monthly model budget and latency SLO?
21. Which observability data may go to LangSmith?
22. Definition of `READY FOR PRODUCTION AGENT`?
23. When should STT/TTS/voice become its own phase?

## 34. Architecture review order

``` text
1. Agent role / prohibited behavior
2. Routing & source-of-truth matrix
3. Safety boundary
4. Doctor Handoff
5. Tool contracts / write permissions
6. Memory / context
7. RAG vs structured lookup
8. Vinmec Web Search
9. Models / cost routing
10. Observability
11. Evaluation
12. Voice/multimodal readiness
13. Implementation breakdown
```

Safety and authority are intentionally reviewed before prompt/model
optimization.

## 35. Draft completion criteria

Agent Architecture V2 is complete only when:

-   responsibilities and prohibited actions are explicit;
-   every important intent has an approved source of truth;
-   tools are typed and authorization-aware;
-   Agent never accesses DB tables directly;
-   patient facts come from authoritative services;
-   Drug Identity uses canonical V2;
-   Safety decisions use Safety Domain;
-   `UNKNOWN` / `REQUIRE_MEDICAL_REVIEW` fail closed;
-   Doctor Handoff works for required cases;
-   Vinmec search is allowlisted and provenance-preserving;
-   RAG/structured boundaries are explicit;
-   memory cannot override clinical state;
-   model choices are configurable;
-   cost/token usage is measurable;
-   Agent runs are auditable;
-   prompt-injection and cross-patient tests pass;
-   local Agent E2E passes;
-   no unresolved P0 remains.

## 36. Expected closeout

``` text
AGENT ARCHITECTURE V2: COMPLETE / INCOMPLETE

P0:
P1:

AGENT CORE:
MODEL GATEWAY:
ROUTING:
TOOLS:
MEMORY:
DRUG KNOWLEDGE:
RAG:
VINMEC WEB SEARCH:
SAFETY:
DOCTOR HANDOFF:
OBSERVABILITY:
EVALUATION:
LOCAL AGENT E2E:

READY FOR VOICE IMPLEMENTATION: YES/NO
READY FOR PRODUCTION AGENT: YES/NO
READY FOR RAILWAY DEPLOYMENT: YES/NO
```

## 37. Immediate next step

Do **not** begin implementation from this draft yet.

Review and approve the architecture section by section, starting with:

**Agent Role, Authority, and Prohibited Behavior**

Then:

**Routing / Source-of-Truth Matrix**

Only after the major architecture decisions are stable should this
become the final Codex implementation plan.

------------------------------------------------------------------------

# 38. Detailed Evaluation Architecture --- Mandatory

This section supersedes any earlier high-level evaluation wording where
more specific requirements are defined here.

Evaluation is a **first-class architecture subsystem and release gate**,
not an optional QA activity. It must support deterministic regression,
LLM-as-a-Judge evaluation, system-performance measurement, safety
evaluation, baseline comparison, and reproducible reporting.

## 38.1 Evaluation layers

``` text
Golden / Versioned Dataset
          ↓
     Actual RAG Pipeline
          ↓
┌───────────────────────────────┐
│ 1. Retrieval Evaluation       │
│ 2. Generation Evaluation      │
│ 3. LLM-as-a-Judge             │
│ 4. System Metrics             │
│ 5. Safety / Agent Evaluation  │
└───────────────┬───────────────┘
                ↓
        Baseline Comparison
                ↓
          Release Gates
           ↙         ↘
         PASS        FAIL
```

A RAG/Agent version must not be promoted solely because sample answers
"look better".

## 38.2 Golden evaluation dataset

Create a deterministic, version-controlled evaluation dataset.

Each case should contain, where applicable:

``` text
case_id
category
query
expected_intent
expected_entities
relevant_document_ids
relevant_chunk_ids
relevance_grades
reference_answer
required_source_type
expected_tool_calls
expected_safety_disposition
doctor_handoff_expected
tags
dataset_version
```

Dataset categories should include at minimum:

``` text
drug identity
indication
contraindication
side effect
interaction
usage
prescription
dose schedule
missed dose
delayed dose
safety-related
general medical knowledge
ambiguous query
no-evidence query
Vinmec web query
doctor-handoff case
```

Evaluation must report both overall metrics and category-level metrics
so strong aggregate performance cannot hide failure in a safety-critical
category.

## 38.3 Deterministic retrieval metrics

Mandatory retrieval metrics:

### Hit Rate@10

Measures whether at least one relevant document/chunk appears in the top
10 retrieved results.

``` text
Hit@10(query) = 1 if any relevant item occurs in top 10
                0 otherwise
```

Report:

``` text
Hit Rate@10 overall
Hit Rate@10 by category
```

### MRR@10

Mean Reciprocal Rank of the first relevant result within the top 10.

Used to measure how early the first useful result appears.

### NDCG@10

Normalized Discounted Cumulative Gain at 10.

Use graded relevance where the golden dataset can distinguish, for
example:

``` text
0 = irrelevant
1 = partially relevant
2 = relevant
3 = highly relevant / authoritative
```

NDCG@10 is especially important when several retrieved chunks are
relevant but differ in usefulness/authority.

### Precision@k

Measure the proportion of top-k retrieved results that are relevant.

Evaluate agreed values of `k`, initially including:

``` text
Precision@3
Precision@5
Precision@10
```

Final k values should reflect the actual number of chunks allowed into
the generation context.

### MAP@k

Mean Average Precision at k across the evaluation set.

Use MAP to evaluate both relevance and ranking consistency across
multiple queries.

### Retrieval reporting

Minimum report:

``` text
Hit Rate@10
MRR@10
NDCG@10
Precision@3
Precision@5
Precision@10
MAP@10
```

Store retrieval configuration alongside results:

``` text
embedding_model
embedding_version
index_version
chunking_version
chunk_size
chunk_overlap
metadata_filter_version
reranker_model/version
top_k
```

## 38.4 Deterministic generation metrics

Mandatory generation regression metrics:

``` text
Exact Match
ROUGE
BLEU
```

### Exact Match

Useful for deterministic/structured questions where a canonical answer
is expected.

Do not treat Exact Match as the only quality metric for natural-language
medical explanations.

### ROUGE

Use to compare overlap with reference answers, particularly for
summaries/explanations.

Record the exact ROUGE variants used in the evaluation implementation.

### BLEU

Use as an additional regression signal for reference-answer similarity.

### Interpretation rule

These metrics are **regression signals**, not standalone
clinical-quality gates.

Semantically equivalent answers can have low lexical overlap. Therefore
generation metrics must be combined with grounding, LLM-as-a-Judge, and
Safety evaluation.

## 38.5 LLM-as-a-Judge

Use an LLM judge to evaluate semantic RAG quality.

The judge model must be configurable:

``` text
RAG_JUDGE_MODEL=
```

GPT-4o may be used as an initial candidate judge, but must not be
hard-coded into the architecture.

The judge must evaluate at least:

### Contextual Relevancy

Question:

> Is the retrieved context relevant to the user's query?

Inputs:

``` text
query
retrieved_context
```

Output should include a normalized score and structured reason/evidence
where supported by the evaluation framework.

### Faithfulness

Question:

> Is the generated answer supported by the retrieved/authoritative
> context?

Inputs:

``` text
query
retrieved_context
generated_answer
```

The metric must penalize unsupported claims/hallucinations.

For medical content, high fluency must never compensate for unsupported
claims.

### Answer Relevancy

Question:

> Does the answer directly and adequately address the user's query?

Inputs:

``` text
query
generated_answer
```

The judge should penalize irrelevant, evasive, or unnecessarily
off-topic responses.

## 38.6 DeepEval

**DeepEval is the primary evaluation framework for LLM/RAG evaluation.**

Use it to build a reproducible test harness covering:

``` text
RAG test cases
LLM-as-a-Judge metrics
custom metrics
thresholds
dataset execution
regression reports
CI/local evaluation
```

The implementation should map DeepEval metrics to the architecture's
canonical metric names rather than allowing framework-specific naming to
leak throughout the application.

DeepEval integration must be replaceable; evaluation datasets/results
must not become unusable if the framework changes later.

## 38.7 System metrics

Mandatory system metrics:

### Latency

Track:

``` text
P50 latency
P95 latency  ← primary latency release gate
P99 latency
```

Measure both:

``` text
end-to-end Agent latency
model latency
retrieval latency
tool latency
web-search latency
Safety Domain latency
Doctor Handoff creation latency
```

### Cost

Track:

``` text
cost/request
cost/1,000 requests
cost/intent
cost/model
cost/user/month
daily projected cost
monthly projected cost
```

Include:

``` text
input tokens
output tokens
cached tokens
embedding usage
judge/evaluation cost
web-search cost where applicable
voice cost when introduced
```

### Embedding drift

Embedding/index changes must be treated as versioned changes.

Detect/compare drift when changing:

``` text
embedding model
embedding model version
normalization
chunking
metadata
source corpus
index configuration
```

Compare new retrieval behavior against the golden dataset and previous
baseline.

A new embedding/index must not silently replace the current production
baseline.

## 38.8 Evaluation baseline

Persist a versioned baseline such as:

``` text
rag_version
dataset_version
embedding_version
index_version
retriever_version
reranker_version
prompt_version
main_model
judge_model

Hit@10
MRR@10
NDCG@10
MAP@10
Precision@k

Exact Match
ROUGE
BLEU

Contextual Relevancy
Faithfulness
Answer Relevancy

P95 latency
cost/query
embedding-drift result
```

Example comparison:

``` text
RAG v1.3 → RAG v1.4

Hit@10       0.91 → 0.94
MRR@10       0.78 → 0.83
NDCG@10      0.82 → 0.86
Faithfulness 0.95 → 0.96
P95          1.8s → 2.1s
Cost/query   X    → Y
```

A quality gain with unacceptable latency/cost regression must be
surfaced rather than hidden.

## 38.9 Release gates

Evaluation must expose independent gates:

``` text
RETRIEVAL QUALITY     PASS / FAIL
GENERATION QUALITY    PASS / FAIL
LLM-JUDGE QUALITY     PASS / FAIL
SYSTEM PERFORMANCE    PASS / FAIL
CLINICAL SAFETY       PASS / FAIL
AUTHORIZATION         PASS / FAIL
```

Then:

``` text
ALL REQUIRED GATES PASS
          ↓
AGENT/RAG RELEASE ELIGIBLE
```

RAG quality PASS **does not imply Clinical Safety PASS**.

A faithful answer that should have been routed to Doctor Handoff can
still cause the Agent release gate to FAIL.

------------------------------------------------------------------------

# 39. Detailed Memory Architecture --- Mandatory

Memory is a separate subsystem from the Operational Database.

``` text
                     AGENT MEMORY
                          │
       ┌──────────────────┼───────────────────┐
       ↓                  ↓                   ↓
 Short-term Memory   Long-term Memory   File-System Offload
       │                  │                   │
       └──────────────────┼───────────────────┘
                          ↓
                  Context Compactor
                          ↓
                   Context Builder
                          ↓
                        LLM
```

## 39.1 Short-term memory

Purpose: preserve information needed for the current
conversation/session.

Examples:

``` text
recent messages
current task
current intent
resolved references
referenced drug
referenced prescription
referenced dose occurrence
pending clarification
recent relevant tool results
current handoff state
```

Short-term memory should be bounded by policy and token budget.

It must not replace authoritative Operational DB lookup for clinical
state.

Example:

``` text
Conversation says:
"Tôi đã uống thuốc"

≠ authoritative TAKEN state

Authoritative state must be confirmed through Dose Domain.
```

## 39.2 Long-term memory

Purpose: retain approved information across sessions when it improves
future interactions.

Long-term memory must be explicitly designed, not implemented as "store
everything".

Each memory record should support metadata such as:

``` text
memory_id
subject/user_id
memory_type
content/reference
source
provenance
created_at
updated_at
last_verified_at
confidence
sensitivity
retention_class
expires_at
status
```

Before enabling long-term memory, approve:

-   allowed memory categories;
-   prohibited categories;
-   consent requirements;
-   retention;
-   deletion/correction;
-   provenance;
-   re-verification;
-   retrieval policy.

Clinical events remain authoritative in Operational DB.

## 39.3 Memory trust rule

A recalled memory cannot override fresher authoritative data.

Example:

``` text
Long-term memory:
"User previously said 2 tablets"

Operational Prescription:
1 tablet

→ Operational Prescription wins.
```

## 39.4 Context Compactor

The Context Compactor activates when context grows too large.

``` text
Raw context
    ↓
Context budget check
    ↓
keep Policy Context
keep protected System Context
keep current Task
keep authoritative current Tool facts
    ↓
remove duplicates
drop irrelevant retrieval
summarize old conversation
offload large artifacts
    ↓
compact context
```

Compaction requirements:

-   never remove mandatory Policy Context;
-   never change authoritative clinical meaning;
-   preserve unresolved Safety/Handoff states;
-   distinguish user claims from verified facts;
-   retain provenance/reference IDs;
-   make compaction auditable/versioned;
-   allow rehydration where possible.

## 39.5 File-System Offload

Large content should not remain indefinitely inside the prompt.

Candidate offload content:

``` text
large retrieved documents
long reports
large tool payloads
conversation exports
intermediate artifacts
large summaries
```

Prompt should retain only:

``` text
artifact/reference ID
metadata
compact summary
retrieval pointer
```

When needed:

``` text
reference
→ targeted retrieval/read
→ relevant range
→ Context Builder
```

File offload must **not** become the authoritative store for
prescriptions, dose state, or Safety decisions.

Production implementation must define durable storage rather than
assuming local ephemeral disk.

## 39.6 Memory retrieval evaluation

Memory retrieval requires its own metrics:

``` text
Memory Hit Rate@k
Memory Precision@k
Memory Recall@k
Stale-memory error rate
Cross-user leakage rate
Clinical-memory override rate
```

Hard gates:

``` text
Cross-user leakage = 0
Clinical-memory override = 0
```

------------------------------------------------------------------------

# 40. Detailed Context Architecture --- Mandatory

The Context Builder must explicitly separate context classes.

``` text
┌─────────────────────────────────────────┐
│ POLICY CONTEXT                          │ ← NEVER DROP
├─────────────────────────────────────────┤
│ SYSTEM CONTEXT                          │ ← PROTECTED
├─────────────────────────────────────────┤
│ TASK CONTEXT                            │
├─────────────────────────────────────────┤
│ USER CONTEXT                            │
├─────────────────────────────────────────┤
│ MEMORY CONTEXT                          │
├─────────────────────────────────────────┤
│ RETRIEVAL CONTEXT                       │
├─────────────────────────────────────────┤
│ TOOL CONTEXT                            │
└─────────────────────────────────────────┘
                    ↓
                  LLM
```

## 40.1 System Context

Contains core Agent identity and behavior:

``` text
persona
Agent identity
communication style
base capabilities
stable behavioral constraints
```

Protected from normal compaction.

## 40.2 Task Context

Contains the current objective:

``` text
current user request
resolved intent
current workflow
task-specific instructions
pending subtask
expected output contract
```

Task Context should remain focused on the active task.

## 40.3 User Context

Contains approved personalization information:

``` text
preferences
language
interaction preferences
relevant historical preferences
```

Do not inject irrelevant personal history merely because it exists.

## 40.4 Memory Context

Contains information recalled from approved memory stores.

Every recalled item should carry provenance, freshness, and trust
metadata.

Memory Context is not automatically authoritative.

## 40.5 Retrieval Context

Contains evidence from:

``` text
RAG
approved internal knowledge
Vinmec Web Search
other approved external retrieval
```

Retrieval Context must be bounded, ranked, source-preserving, and
treated as untrusted instructions.

## 40.6 Tool Context

Contains structured results from tools/APIs:

``` text
Operational DB tools
Drug Knowledge tools
Dose tools
Safety tools
Doctor Handoff tools
```

Tool Context can contain high-authority facts and must preserve
source/service identity and freshness.

## 40.7 Policy Context --- highest priority

Contains:

``` text
security rules
authorization rules
clinical safety rules
tool permissions
Doctor Handoff rules
privacy constraints
guardrails
prohibited actions
```

**Policy Context is never dropped because of context pressure.**

No User, Memory, Retrieval, Tool, or web content may override Policy
Context.

## 40.8 Context item metadata

Context priority and trust are separate concepts.

Each context item should support:

``` text
source
authority
priority
freshness
sensitivity
token_cost
provenance
verification_status
```

Conflict resolution must prefer authoritative/fresher sources according
to domain rules, not simply whichever text appeared later.

## 40.9 Context Budget Manager

Introduce a dedicated Context Budget Manager.

``` text
Policy Context             NEVER DROP
System Context             PROTECTED
Current Task               HIGH
Authoritative Tool Context HIGH
Relevant Retrieval         DYNAMIC
Relevant Memory            DYNAMIC
Recent Conversation        DYNAMIC
Old Conversation           COMPACT/OFFLOAD
```

Configuration should support:

``` text
MAX_CONTEXT_TOKENS=
CONTEXT_OUTPUT_RESERVE=
MAX_MEMORY_CONTEXT_TOKENS=
MAX_RETRIEVAL_CONTEXT_TOKENS=
MAX_TOOL_CONTEXT_TOKENS=
MAX_RECENT_MESSAGE_TOKENS=
```

Never fill the entire model context window. Reserve capacity for model
output and tool-loop continuation.

Budget flow:

``` text
estimate tokens
    ↓
within budget?
 ├─ YES → execute
 └─ NO
      ↓
remove irrelevant retrieval
      ↓
compact old conversation
      ↓
offload large artifacts
      ↓
retrieve only necessary references
      ↓
recalculate
      ↓
still too large?
      ↓
fail gracefully / ask focused clarification
```

Invariant:

> Context compaction may reduce detail, but must never remove
> Safety/Policy constraints or alter authoritative clinical state.

------------------------------------------------------------------------

# 41. Observability & Guardrails --- Mandatory

Guardrails control the Agent **while it runs**.

Observability explains **what the Agent did**.

Checkpointing records **where execution reached** and supports safe
recovery.

``` text
User Request
     ↓
┌──────────────────────────────┐
│       AGENT GUARDRAILS       │
│ Security / Authorization     │
│ Clinical Safety              │
│ Token Budget                 │
│ Step Budget                  │
│ Tool-call Budget             │
│ Timeout / Loop Detection     │
└──────────────┬───────────────┘
               ↓
          AGENT RUNTIME
               ↓
       Models ↔ Tools
               ↓
           CHECKPOINTS
               ↓
          Final Response
               ↓
┌──────────────────────────────┐
│       OBSERVABILITY          │
│ Logging                      │
│ Tracing                      │
│ Metrics / Cost               │
│ Monitoring                   │
│ Alerts                       │
│ Evaluation                   │
└──────────────────────────────┘
```

## 41.1 Token guardrails

Mandatory configurable budgets:

``` text
MAX_INPUT_TOKENS=
MAX_OUTPUT_TOKENS=
MAX_TOTAL_TOKENS_PER_RUN=
MAX_RETRIEVAL_TOKENS=
MAX_MEMORY_TOKENS=
MAX_TOOL_RESULT_TOKENS=
```

Token pressure should invoke Context Budget Manager/Compactor before
failing.

Policy Context must never be removed to satisfy a token budget.

## 41.2 Agent-step guardrails

Do not expose/store hidden chain-of-thought. Limit observable
orchestration steps instead.

Configuration:

``` text
MAX_AGENT_STEPS=
MAX_MODEL_CALLS=
MAX_TOOL_CALLS=
MAX_RETRIES_PER_TOOL=
MAX_SAME_TOOL_CALLS=
MAX_RUN_DURATION_MS=
```

Example loop:

``` text
search_drug
→ search_drug
→ search_drug
→ search_drug
```

must trigger loop detection/termination.

If a Safety-relevant run exhausts its budget:

``` text
budget exceeded
+ safety unresolved
→ fail closed
→ safe fallback / Doctor Handoff
```

Never guess because the step budget ended.

## 41.3 Tool-call guardrails

Support per-tool limits, for example:

``` text
search_drug            bounded
RAG retrieval          bounded
Vinmec search          bounded
get_today_doses        bounded
Safety assessment      controlled
Doctor Handoff         idempotent
```

Exact numeric defaults must be established through evaluation.

Tool permission classes remain:

``` text
READ_ONLY
LOW_RISK_WRITE
SENSITIVE_WRITE
CLINICAL_WRITE
```

Permission enforcement must occur server-side before execution, not only
in prompts.

## 41.4 Timeout and retry policy

Define:

``` text
per-model timeout
per-tool timeout
overall Agent-run timeout
retryable error classes
non-retryable error classes
retry count
backoff policy
```

Writes require idempotency before automatic retry.

## 41.5 Structured logging

Log structured events including:

``` text
timestamp
request_id
conversation_id
agent_run_id
actor_role
intent
model
model_version
prompt_version
tool_name
tool_status
latency_ms
input_tokens
output_tokens
cached_tokens
estimated_cost
safety_disposition
doctor_handoff
final_status
error_code
```

Never log:

``` text
passwords
secrets
raw access tokens
unnecessary PII
hidden chain-of-thought
```

Clinical/user content requires explicit minimization/redaction rules.

## 41.6 Distributed tracing

A trace should show the execution path:

``` text
TRACE agent_run_x

HTTP request
├─ context.resolve
├─ model.router
├─ tool.get_today_doses
├─ model.orchestrator
├─ tool.assess_missed_dose
├─ doctor_handoff (if required)
└─ model.response

TOTAL LATENCY
TOKEN USAGE
ESTIMATED COST
FINAL STATUS
```

Each major component should emit a span.

LangSmith may visualize Agent/RAG traces and evaluations, but the
internal trace contract must remain vendor-neutral.

## 41.7 Checkpoints

Checkpoint **execution state**, not hidden reasoning.

Candidate checkpoint:

``` text
checkpoint_id
agent_run_id
step_number
workflow_state
completed_tools
resolved_entities
verified_context_refs
safety_disposition
pending_action
created_at
```

Example:

``` text
Checkpoint 1
intent = MISSED_DOSE
dose_occurrence = X

Checkpoint 2
Safety assessment completed
disposition = REQUIRE_MEDICAL_REVIEW

Checkpoint 3
Doctor Handoff created
handoff_id = Y
```

Checkpointing should enable safe recovery without replaying every
completed side effect.

## 41.8 Checkpoint + idempotency

All retriable write actions must combine:

``` text
checkpoint
+ idempotency key
+ transaction/domain semantics
```

Example:

``` text
request_doctor_review()
→ server creates request
→ network timeout
→ Agent retries same idempotency key
→ existing request returned
→ NO duplicate doctor request
```

The same principle applies to dose-state writes.

## 41.9 Run terminal states

Every Agent run must end in a defined state:

``` text
COMPLETED
FAILED
BUDGET_EXCEEDED
TIMEOUT
SAFETY_BLOCKED
HANDOFF_REQUIRED
HANDOFF_CREATED
CANCELLED
```

No run should remain silently unresolved.

## 41.10 Monitoring

Dashboards should include:

### Traffic

``` text
requests/min
active conversations
requests by intent
```

### Quality

``` text
RAG retrieval metrics
LLM-judge metrics
handoff rate
tool failure rate
```

### Performance

``` text
P50
P95
P99
```

### Model/cost

``` text
model calls
input/output/cached tokens
cost/request
cost/day
projected monthly cost
```

### Tools

``` text
tool latency
tool errors
timeouts
retry rate
```

### Context/Memory

``` text
context overflow rate
compaction rate
offload rate
memory recall rate
stale-memory errors
```

### Safety

``` text
REQUIRE_MEDICAL_REVIEW rate
UNKNOWN rate
Doctor Handoff rate
Safety Domain failures
handoff failures
```

### Runtime

``` text
Agent failure rate
budget-exceeded rate
loop-termination rate
checkpoint recovery rate
```

## 41.11 Alerts

Define alert thresholds for at least:

``` text
P95 latency regression
tool error-rate spike
daily/monthly cost budget
context-overflow spike
Agent failure spike
RAG-quality regression
embedding drift
```

High-priority/critical alerts:

``` text
Safety Domain unavailable
cross-patient authorization violation
required Doctor Handoff bypassed
unexpected clinical write attempt
Policy Context construction failure
```

## 41.12 Guardrail hierarchy

Mandatory priority:

``` text
1. SECURITY / AUTHORIZATION
2. CLINICAL SAFETY POLICY
3. DOCTOR HANDOFF POLICY
4. TOOL PERMISSIONS
5. TOKEN / STEP / TIME BUDGET
6. TASK INSTRUCTIONS
7. USER REQUEST
```

Lower layers cannot override higher layers.

Example:

``` text
User:
"Đừng hỏi bác sĩ, cứ nói tôi uống gấp đôi được không."

→ User request cannot override Safety / Doctor Handoff policy.
```

------------------------------------------------------------------------

# 42. Updated Agent Core Architecture

With the detailed Memory, Context, Evaluation, Observability, and
Guardrail requirements, the target Agent Core becomes:

``` text
                         USER
                          ↓
                    Input Adapter
                          ↓
                 Auth / Authorization
                          ↓
┌────────────────────────────────────────────┐
│                 GUARDRAILS                 │
│ Security / Authorization                   │
│ Clinical Safety / Handoff                  │
│ Token / Step / Tool-call Budgets           │
│ Timeout / Retry / Loop Detection           │
└─────────────────────┬──────────────────────┘
                      ↓
┌────────────────────────────────────────────┐
│               CONTEXT MANAGER              │
│ Policy Context            NEVER DROP       │
│ System Context            PROTECTED        │
│ Task Context                               │
│ User Context                               │
│ Memory Context ← Memory subsystem          │
│ Retrieval Context ← RAG / Vinmec Web       │
│ Tool Context ← Domain tools                │
│                                            │
│ Context Budget Manager                     │
│ Context Compactor                          │
│ File-System Offload / Recall               │
└─────────────────────┬──────────────────────┘
                      ↓
                 AGENT RUNTIME
                      ↓
                 Model Gateway
                      ↓
                Tool Orchestrator
                      ↓
     ┌────────────────┼──────────────────┐
     ↓                ↓                  ↓
Operational       Knowledge          Safety Domain
DB / Drug V2      RAG/Vinmec              ↓
                                    Doctor Handoff
                      ↓
                  Checkpoint
                      ↓
               Response Composer
                      ↓
                 Output Adapter
                      ↓
                     USER

Cross-cutting:
Logging / Tracing / Metrics / Monitoring / Alerts
DeepEval / Deterministic Evaluation / Release Gates
```

------------------------------------------------------------------------

# 43. Updated implementation workstreams

The earlier AG workstreams are refined as follows:

``` text
AG-1   Current Agent Audit
AG-2   Agent Boundary & Authority
AG-3   Context Architecture
AG-4   Memory Architecture
AG-5   Model Gateway & Cost-Aware Routing
AG-6   Tool Gateway & Core Domain Tools
AG-7   RAG / Retrieval Architecture
AG-8   Vinmec Web Search
AG-9   Safety & Action Guardrails
AG-10  Doctor Handoff
AG-11  Agent Runtime / Orchestration
AG-12  Checkpoint / Recovery / Idempotency
AG-13  Observability / Logging / Tracing / Monitoring
AG-14  Deterministic RAG Evaluation
AG-15  DeepEval + LLM-as-a-Judge
AG-16  Security / Prompt-Injection / Authorization Red Team
AG-17  Local Agent E2E
AG-18  Agent Architecture Closeout
```

Voice/STT/TTS remains architecturally supported but is a later
implementation phase unless explicitly brought into scope.

------------------------------------------------------------------------

# 44. Updated architecture completion gates

Agent Architecture V2 cannot close unless all of the following are
explicitly validated:

``` text
AGENT BOUNDARY: PASS
CONTEXT ARCHITECTURE: PASS
POLICY CONTEXT NEVER-DROP: PASS
SHORT-TERM MEMORY: PASS
LONG-TERM MEMORY POLICY: PASS
CONTEXT COMPACTION: PASS
FILE OFFLOAD: PASS

TOOL AUTHORIZATION: PASS
SAFETY DOMAIN BOUNDARY: PASS
DOCTOR HANDOFF: PASS

TOKEN GUARDRAILS: PASS
STEP/TOOL GUARDRAILS: PASS
TIMEOUT/LOOP GUARDRAILS: PASS
CHECKPOINT/RECOVERY: PASS
WRITE IDEMPOTENCY: PASS

RAG RETRIEVAL EVAL: PASS
GENERATION EVAL: PASS
DEEPEVAL LLM-JUDGE: PASS
SYSTEM METRICS: PASS
EMBEDDING DRIFT GATE: PASS
CLINICAL SAFETY EVAL: PASS

LOGGING: PASS
TRACING: PASS
MONITORING: PASS
ALERTING: PASS

LOCAL AGENT E2E: PASS
P0: 0
```

------------------------------------------------------------------------

# 45. Approved Initial Model Stack

The current OpenAI API project/key has been checked through `/v1/models`
and the required model families are visible to the project.

Initial architecture mapping:

``` text
AGENT_ROUTER_MODEL=gpt-5.4-nano
AGENT_MAIN_MODEL=gpt-5.4-mini
AGENT_FALLBACK_MODEL=gpt-5.4
EMBEDDING_MODEL=text-embedding-3-small
RAG_JUDGE_MODEL=gpt-4o
```

Future voice-ready candidates visible to the current API project
include:

``` text
STT_MODEL=gpt-4o-mini-transcribe
TTS_MODEL=gpt-4o-mini-tts
REALTIME_MODEL=<to be benchmarked before voice implementation>
```

The realtime model is intentionally not pinned yet. Voice implementation
is outside the initial build scope.

## 45.1 Model responsibilities

### `gpt-5.4-nano` --- Router

Primary responsibilities:

-   intent classification;
-   lightweight entity extraction;
-   route selection;
-   structured routing output;
-   determining whether the request can take a deterministic/tool-first
    path.

The dedicated Router remains subject to evaluation. If end-to-end
evaluation proves that the Main Agent can route more reliably and
cheaply, the Router may be removed.

### `gpt-5.4-mini` --- Main Agent

Primary responsibilities:

-   understand current context;
-   orchestrate approved tools;
-   consume authoritative tool results;
-   use retrieved evidence;
-   resolve conversational references;
-   generate grounded user-facing responses.

This is the default production candidate and must pass Vietnamese
medical-domain evaluation before rollout.

### `gpt-5.4` --- Fallback

Used only for approved difficult non-clinical orchestration/reasoning
cases where the Main Agent is insufficient.

Rules:

-   must not replace Safety Domain;
-   must not replace Doctor Handoff;
-   must have a configurable usage/cost limit;
-   fallback rate must be monitored.

### `text-embedding-3-small` --- Retrieval embedding

Initial embedding candidate for:

-   RAG indexing;
-   RAG query embedding;
-   approved semantic memory retrieval.

Embedding versions and index versions must be recorded for deterministic
evaluation and embedding-drift checks.

### `gpt-4o` --- Evaluation Judge

Initial LLM-as-a-Judge candidate for DeepEval:

-   Contextual Relevancy;
-   Faithfulness;
-   Answer Relevancy.

Judge calls are primarily for offline/CI/pre-release evaluation and
controlled production sampling, not every production user request.

## 45.2 Model Gateway configuration

Model selection must be configuration-driven:

``` text
MODEL_GATEWAY
├── router
│   ├── model
│   ├── api_key_ref
│   ├── project/account_ref
│   ├── token_budget
│   └── rate_limit
├── main
│   ├── model
│   ├── api_key_ref
│   ├── project/account_ref
│   ├── token_budget
│   └── rate_limit
├── fallback
├── embedding
├── judge
└── future_voice
```

The Agent Core must not contain hard-coded API keys.

Support separate API credentials/projects/accounts per workload where
operationally required, while keeping the Agent Core provider/key
agnostic.

Suggested environment contract:

``` text
OPENAI_ROUTER_API_KEY=
OPENAI_MAIN_API_KEY=
OPENAI_FALLBACK_API_KEY=
OPENAI_EMBEDDING_API_KEY=
OPENAI_JUDGE_API_KEY=

AGENT_ROUTER_MODEL=gpt-5.4-nano
AGENT_MAIN_MODEL=gpt-5.4-mini
AGENT_FALLBACK_MODEL=gpt-5.4
EMBEDDING_MODEL=text-embedding-3-small
RAG_JUDGE_MODEL=gpt-4o
```

For development, these keys may point to the same OpenAI project.
Production must allow them to be separated without changing Agent
business logic.

## 45.3 Pre-build model smoke test

Before relying on a model in runtime, perform one minimal real API smoke
test for:

``` text
gpt-5.4-nano
gpt-5.4-mini
gpt-5.4
text-embedding-3-small
gpt-4o
```

Validate:

``` text
model permission
endpoint compatibility
authentication
quota/billing
rate-limit behavior
structured output/tool compatibility where applicable
```

Model visibility from `/v1/models` is accepted as discovery evidence,
but runtime smoke tests are the implementation gate.

## 45.4 Cost telemetry

For every runtime model call record:

``` text
model
account/project reference
input_tokens
cached_input_tokens
output_tokens
estimated_cost
request_id
agent_run_id
intent
```

Cost dashboards must separate:

``` text
Router
Main Agent
Fallback
Embedding
Judge/Evaluation
Future Voice
```

Complimentary/free-token programs must be treated as billing
optimization, not as an architectural dependency. The system must remain
operable if complimentary quota changes or disappears.

------------------------------------------------------------------------

# 46. Build Readiness and Implementation Start

Architecture planning is now sufficiently detailed to begin
implementation **incrementally behind feature flags**, while preserving
the existing audited application/domain boundaries.

Do not build all subsystems simultaneously.

## 46.1 Build order

Start in this order:

``` text
BUILD-0  Repository / Current Agent Audit
   ↓
BUILD-1  Agent Boundary + Runtime Skeleton
   ↓
BUILD-2  Model Gateway + Model Smoke Tests
   ↓
BUILD-3  Guardrails + Run State
   ↓
BUILD-4  Context Manager
   ↓
BUILD-5  Short-Term Memory
   ↓
BUILD-6  Tool Gateway + Read-Only Domain Tools
   ↓
BUILD-7  RAG Retrieval
   ↓
BUILD-8  Vinmec Web Search
   ↓
BUILD-9  Safety Integration
   ↓
BUILD-10 Doctor Handoff
   ↓
BUILD-11 Long-Term Memory / Compactor / Offload
   ↓
BUILD-12 Checkpoint / Recovery / Idempotency
   ↓
BUILD-13 Observability
   ↓
BUILD-14 Deterministic RAG Evaluation
   ↓
BUILD-15 DeepEval / LLM-as-a-Judge
   ↓
BUILD-16 Security / Red Team
   ↓
BUILD-17 Local Frontend E2E
   ↓
BUILD-18 Closeout
```

## 46.2 First implementation milestone

The first milestone should **not** attempt full RAG, Doctor Handoff,
long-term memory, or voice.

Target:

``` text
Frontend local chat
      ↓
Agent endpoint
      ↓
Auth/context
      ↓
Model Gateway
      ↓
gpt-5.4-nano router
      ↓
gpt-5.4-mini main agent
      ↓
READ-ONLY approved tools
      ↓
grounded response
      ↓
logging / agent_run
```

Initial read-only tools should prioritize:

``` text
search_drug
get_drug_info
get_active_prescriptions
get_today_doses
get_upcoming_doses
get_dose_status
```

No prescription modification.

No autonomous clinical write.

No Safety decision recreated in prompts.

## 46.3 First milestone acceptance criteria

``` text
[ ] Current Agent implementation audited.
[ ] New Agent path protected by feature flag.
[ ] Model Gateway exists.
[ ] All five initial models pass smoke tests.
[ ] API keys remain backend-only.
[ ] Router returns typed/structured output.
[ ] Main Agent can call approved read-only tools.
[ ] Patient authorization enforced server-side.
[ ] Agent cannot query ORM/tables directly.
[ ] Token/step/tool-call budgets exist.
[ ] Agent run has terminal status.
[ ] Basic structured logging/tracing exists.
[ ] Existing application behavior remains unchanged with Agent flag OFF.
[ ] Local frontend can complete at least one grounded read-only Agent flow.
```

## 46.4 Implementation safety rule

During early build stages:

``` text
READ path first
→ evaluate
→ Safety integration
→ Doctor Handoff
→ only then consider controlled WRITE actions
```

Do not expose dose/prescription write actions merely to demonstrate
Agent tool calling.

## 46.5 Recommended first coding task

Begin with:

> **BUILD-0 --- Current Agent Audit + Implementation Mapping**

The coding agent should inspect the repository and produce a factual
implementation map before changing code:

``` text
existing chatbot endpoints
existing model clients
existing prompts
existing conversation/message persistence
existing RAG/index/vector code
existing auth/patient-context flow
existing Drug V2 services
existing Prescription/Dose services
existing Safety services
existing feature flags
existing frontend chat integration
existing observability/tests
```

Output:

``` text
CURRENT STATE
REUSABLE COMPONENTS
GAPS
CONFLICTS WITH ARCHITECTURE
FILES/MODULES TO CHANGE
PROPOSED BUILD-1 IMPLEMENTATION
P0/P1 RISKS
```

BUILD-0 must not introduce schema migrations or broad refactors.
