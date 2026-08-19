# Database Architecture V2 Plan

## 1. Mục tiêu

Thiết kế lại database cho app nhắc lịch uống thuốc theo hướng:

-   Tách rõ **Drug Knowledge** khỏi dữ liệu vận hành của bệnh nhân.
-   Quản lý đúng vòng đời: đơn thuốc → kế hoạch dùng thuốc → lịch uống →
    từng liều → hành vi thực tế.
-   Hỗ trợ missed/delayed dose, notification, safety escalation và
    Agent.
-   Có audit trail, versioning và migration an toàn từ database hiện
    tại.
-   Không làm thay đổi Final Canonical Drug V2 đã hoàn thành.

------------------------------------------------------------------------

## 2. Nguyên tắc kiến trúc

### 2.1. Tách 4 domain chính

``` text
Drug Knowledge
    ↓ reference

Patient / Prescription
    ↓

Medication Scheduling
    ↓

Safety / Agent / Notification
```

Không copy toàn bộ thông tin thuốc vào prescription hoặc lịch uống.

### 2.2. `drug_product_id` là liên kết chuẩn

Các bảng nghiệp vụ chỉ reference thuốc bằng ID.

``` text
drug_product
      ↑
prescription_item
      ↑
medication_plan
```

Giữ compatibility với `legacy_drug_id` trong giai đoạn migration.

### 2.3. Không dùng category risk như medical truth

Risk theo nhóm thuốc V1 chỉ được migrate thành **default/fallback
policy**:

``` text
source = LEGACY_CATEGORY_RULE
review_status = NOT_CLINICALLY_REVIEWED
```

Drug/ingredient-specific policy có thể override category policy.

------------------------------------------------------------------------

# 3. Target Domain Model

## 3.1. Patient

### `patient`

``` text
id
user_id
display_name
date_of_birth
sex
timezone
status
created_at
updated_at
```

Không lưu dữ liệu không cần thiết cho chatbot.

------------------------------------------------------------------------

## 3.2. Prescription

### `prescription`

Đại diện cho một đơn thuốc.

``` text
id
patient_id
status
prescribed_by
prescribed_at
start_date
end_date
notes
created_at
updated_at
```

Status ví dụ:

``` text
DRAFT
ACTIVE
COMPLETED
CANCELLED
```

### `prescription_item`

Một thuốc trong đơn.

``` text
id
prescription_id
drug_product_id
legacy_drug_id
dose_text
dose_value
dose_unit
route
frequency_text
instructions
start_date
end_date
created_at
updated_at
```

`dose_text` giữ raw prescription; structured fields chỉ dùng khi parse
chắc chắn.

------------------------------------------------------------------------

# 4. Medication Plan

### `medication_plan`

Kế hoạch dùng một thuốc cụ thể của bệnh nhân.

``` text
id
patient_id
prescription_item_id
drug_product_id
status
timezone
start_at
end_at
instructions
created_at
updated_at
```

Một prescription item có thể sinh ra medication plan.

------------------------------------------------------------------------

# 5. Scheduling

## 5.1. `schedule_rule`

Mô tả quy luật uống thuốc.

``` text
id
medication_plan_id
rule_type
frequency
interval_value
interval_unit
times_of_day
days_of_week
start_at
end_at
timezone
created_at
updated_at
```

Ví dụ:

``` text
DAILY
INTERVAL
WEEKLY
CUSTOM
```

Không dùng Agent để tự suy diễn schedule khi prescription không rõ.

------------------------------------------------------------------------

## 5.2. `dose_occurrence`

Đây là bảng quan trọng nhất của reminder engine.

Mỗi row = **một liều đáng lẽ bệnh nhân phải dùng**.

``` text
id
medication_plan_id
scheduled_at
status
due_at
grace_until
taken_at
created_at
updated_at
```

Status:

``` text
SCHEDULED
DUE
TAKEN
MISSED
SKIPPED
DELAYED
CANCELLED
```

Ví dụ:

``` text
Medication Plan
    ↓
08:00 dose
    ↓
dose_occurrence
scheduled_at = 08:00
```

------------------------------------------------------------------------

# 6. Dose Event

### `dose_event`

Lưu hành động thực tế của bệnh nhân.

``` text
id
dose_occurrence_id
patient_id
event_type
event_at
source
metadata
created_at
```

Event:

``` text
TAKEN
SKIPPED
SNOOZED
MISSED_CONFIRMED
MANUAL_CORRECTION
```

`dose_occurrence` là trạng thái hiện tại.

`dose_event` là lịch sử bất biến.

------------------------------------------------------------------------

# 7. Notification

### `notification_job`

``` text
id
patient_id
dose_occurrence_id
notification_type
scheduled_at
status
attempt_count
sent_at
provider
created_at
updated_at
```

Status:

``` text
PENDING
SENT
FAILED
CANCELLED
```

Không dùng notification table làm source-of-truth cho dose status.

------------------------------------------------------------------------

# 8. Medication Safety Policy

Đây là phần thay thế `muc_nghiem_trong` V1.

### `medication_safety_policy`

``` text
id
scope_type
scope_id
risk_type
risk_level
action_policy
source_type
source_reference
review_status
policy_version
valid_from
valid_to
created_at
updated_at
```

### `scope_type`

``` text
CATEGORY
INGREDIENT
DRUG_PRODUCT
```

### `risk_type`

Ban đầu:

``` text
MISSED_DOSE
DELAYED_DOSE
```

Có thể mở rộng:

``` text
INTERACTION
CONTRAINDICATION
PREGNANCY
```

### `risk_level`

``` text
LOW
MODERATE
HIGH
CRITICAL
UNKNOWN
```

### `review_status`

``` text
LEGACY_UNREVIEWED
REVIEW_REQUIRED
REVIEWED
REJECTED
```

------------------------------------------------------------------------

# 9. Risk Resolution

Policy resolution theo độ ưu tiên:

``` text
Drug Product Policy
        ↓
Ingredient / Drug Class Policy
        ↓
Category Default Policy
        ↓
UNKNOWN / Safe fallback
```

Không để category tự override drug-specific evidence.

------------------------------------------------------------------------

# 10. Missed Dose Assessment

### `missed_dose_assessment`

Lưu kết quả đánh giá khi bệnh nhân trễ/quên liều.

``` text
id
patient_id
medication_plan_id
dose_occurrence_id
drug_product_id
risk_level
recommended_action
policy_id
reason_code
assessment_version
evaluated_at
created_at
```

`recommended_action`:

``` text
LOG_ONLY
REMIND
WARN
ESCALATE_CAREGIVER
ESCALATE_CLINICIAN
REQUIRE_MEDICAL_REVIEW
```

Không tự sinh hướng dẫn y khoa cụ thể nếu policy/evidence không hỗ trợ.

------------------------------------------------------------------------

# 11. Safety Event

### `safety_event`

Dùng cho các sự kiện cần audit/escalation.

``` text
id
patient_id
conversation_id
dose_occurrence_id
drug_product_id
event_type
severity
decision
reason
created_at
```

Ví dụ:

``` text
MISSED_HIGH_RISK_DOSE
RED_FLAG_SYMPTOM
DRUG_INTERACTION_WARNING
AMBIGUOUS_DRUG
```

------------------------------------------------------------------------

# 12. Conversation / Agent

### `conversation`

``` text
id
patient_id
status
started_at
last_message_at
created_at
```

### `message`

``` text
id
conversation_id
role
content
created_at
```

Không nên biến conversation history thành medical source-of-truth.

Các quyết định quan trọng phải được ghi riêng trong domain tables.

------------------------------------------------------------------------

# 13. Agent Audit

### `agent_run`

``` text
id
conversation_id
patient_id
request_id
intent
status
started_at
completed_at
created_at
```

### `agent_tool_event`

``` text
id
agent_run_id
tool_name
input_reference
output_reference
status
latency_ms
created_at
```

Không lưu chain-of-thought.

Chỉ lưu decision/tool trace cần thiết để audit.

LangSmith sẽ được thiết kế sau ở Observability phase.

------------------------------------------------------------------------

# 14. Audit Log

### `audit_log`

``` text
id
actor_type
actor_id
entity_type
entity_id
action
before_snapshot
after_snapshot
request_id
created_at
```

Các thay đổi quan trọng như prescription, medication plan, schedule và
safety policy phải audit được.

------------------------------------------------------------------------

# 15. Quan hệ tổng thể

``` text
patient
   │
   ├── prescription
   │       │
   │       └── prescription_item ─────→ drug_product
   │                     │
   │                     ↓
   │              medication_plan
   │                     │
   │                schedule_rule
   │                     │
   │                     ↓
   │              dose_occurrence
   │                │          │
   │                ↓          ↓
   │           dose_event   notification_job
   │                │
   │                ↓
   │       missed_dose_assessment
   │                │
   │                ↓
   │           safety_event
   │
   └── conversation
            │
          message
            │
         agent_run
            │
      agent_tool_event
```

Safety policy đứng riêng:

``` text
drug_category ─────┐
ingredient ────────┼→ medication_safety_policy
drug_product ──────┘
                         ↓
                 missed-dose evaluator
```

------------------------------------------------------------------------

# 16. Database Constraints

Phải thiết kế:

-   Foreign keys.
-   Unique constraints.
-   Check constraints cho enum/status quan trọng.
-   UTC timestamp + timezone rõ ràng.
-   Không hard delete dữ liệu y tế/audit quan trọng nếu chưa có policy.
-   Index cho các truy vấn reminder/retrieval thường xuyên.

Index ưu tiên:

``` text
dose_occurrence(medication_plan_id, scheduled_at)
dose_occurrence(status, scheduled_at)
notification_job(status, scheduled_at)
prescription(patient_id, status)
medication_plan(patient_id, status)
medication_safety_policy(scope_type, scope_id, risk_type)
safety_event(patient_id, created_at)
```

------------------------------------------------------------------------

# 17. Transaction Boundaries

Các operation cần atomic transaction:

### Create prescription

``` text
prescription
+ prescription_items
```

### Activate medication plan

``` text
medication_plan
+ schedule_rule
+ initial dose occurrences
```

### Mark dose taken

``` text
dose_event(TAKEN)
+ dose_occurrence.status = TAKEN
+ cancel pending reminder
```

### Safety escalation

``` text
missed_dose_assessment
+ safety_event
+ escalation notification
```

------------------------------------------------------------------------

# 18. Idempotency

Reminder/scheduler phải chống duplicate.

Cần idempotency key cho:

``` text
dose generation
notification dispatch
dose-event writes
external callbacks
```

Không được để restart worker sinh hai `dose_occurrence` giống nhau.

------------------------------------------------------------------------

# 19. Migration Strategy

Không rewrite database một lần.

## Phase DB-1 --- Audit

Audit schema/code hiện tại:

-   tables;
-   migrations;
-   ORM models;
-   foreign keys;
-   API dependencies;
-   prescription logic;
-   reminder logic;
-   Agent DB access;
-   V1/V2 drug ID usage.

Output:

``` text
current-db-audit.md
```

------------------------------------------------------------------------

## Phase DB-2 --- Target Schema Design

Tạo:

``` text
target-schema.md
erd.md
migration-map.md
```

Chưa migrate.

Review schema trước.

------------------------------------------------------------------------

## Phase DB-3 --- Additive Migration

Chỉ thêm tables/columns mới.

Không drop V1.

Ví dụ:

``` text
medication_plan
schedule_rule
dose_occurrence
dose_event
medication_safety_policy
missed_dose_assessment
safety_event
```

------------------------------------------------------------------------

## Phase DB-4 --- Compatibility Layer

Backend có thể đọc V1/V2 trong thời gian migration.

``` text
old prescription
      ↓
compatibility adapter
      ↓
new domain services
```

Không breaking public API ngay.

------------------------------------------------------------------------

## Phase DB-5 --- Backfill

Backfill:

``` text
legacy prescriptions
→ prescription/prescription_item

legacy schedules
→ medication_plan/schedule_rule
```

Có validation report.

------------------------------------------------------------------------

## Phase DB-6 --- Safety Policy Migration

Migrate V1 category severity thành fallback policy:

``` text
muc_nghiem_trong
      ↓
CATEGORY / MISSED_DOSE policy
```

Metadata bắt buộc:

``` text
source_type = LEGACY_CATEGORY_RULE
review_status = LEGACY_UNREVIEWED
```

Không promote thành reviewed medical fact.

------------------------------------------------------------------------

## Phase DB-7 --- Domain Cutover

Chuyển:

``` text
prescription service
reminder engine
Agent tools
```

sang schema/domain V2.

Giữ rollback.

------------------------------------------------------------------------

## Phase DB-8 --- Stabilization

Chạy:

-   DB integrity tests;
-   concurrency tests;
-   reminder duplication tests;
-   timezone tests;
-   missed/delayed tests;
-   prescription regression;
-   Agent regression;
-   rollback tests.

Sau stabilization mới xem xét deprecate schema cũ.

------------------------------------------------------------------------

# 20. Database Architecture Acceptance Criteria

Database Architecture chỉ được coi là hoàn thành khi:

``` text
[ ] Current DB audit hoàn chỉnh
[ ] Target ERD/schema được review
[ ] Drug Knowledge tách khỏi operational data
[ ] Prescription model rõ ràng
[ ] Medication Plan model rõ ràng
[ ] Schedule Rule model rõ ràng
[ ] Dose Occurrence/Event model rõ ràng
[ ] Notification model rõ ràng
[ ] Safety Policy model rõ ràng
[ ] Category risk chỉ là fallback
[ ] Missed-dose assessment có audit trail
[ ] Migration/backfill strategy rõ ràng
[ ] Backwards compatibility rõ ràng
[ ] Transaction boundaries được định nghĩa
[ ] Idempotency strategy được định nghĩa
[ ] Index strategy được định nghĩa
[ ] Không breaking public API ngoài kế hoạch
[ ] Rollback strategy tồn tại
```

------------------------------------------------------------------------

# 21. Những việc KHÔNG làm trong Database Architecture

-   Không sửa lại Data Foundation nếu không có lỗi cụ thể.
-   Không re-crawl thuốc.
-   Không dùng LLM để quyết định medical risk.
-   Không tự suy ra missed-dose instructions từ drug category.
-   Không xóa schema V1 trước stabilization.
-   Không deploy Railway trong giai đoạn thiết kế.
-   Chưa cần LangSmith.
-   Không thiết kế Agent prompt trong phase này.

------------------------------------------------------------------------

# 22. Deliverables

Lưu report/design tại:

``` text
data pharmacy/reports/database-architecture/
```

Dự kiến:

``` text
01-current-db-audit.md
02-domain-model.md
03-target-schema.md
04-erd.md
05-safety-policy-model.md
06-migration-strategy.md
07-index-transaction-idempotency.md
08-database-architecture-final-review.md
```

------------------------------------------------------------------------

# 23. Thứ tự triển khai

``` text
Data Foundation                 DONE
        ↓
Current DB Audit                NEXT
        ↓
Domain Model
        ↓
Target Schema + ERD
        ↓
Safety Policy Schema
        ↓
Migration Strategy
        ↓
Review / Approve Architecture
        ↓
Additive DB Migration
        ↓
Backfill
        ↓
Domain Services
        ↓
Reminder Engine
        ↓
Safety Architecture
        ↓
Agent Architecture
```

------------------------------------------------------------------------

# 24. Bước tiếp theo

**Chưa code migration ngay.**

Task đầu tiên:

> Audit toàn bộ database, ORM, migrations, prescription/reminder flow và
> các dependency hiện tại; sau đó lập `01-current-db-audit.md`.

Sau audit mới thiết kế schema dựa trên trạng thái thật của repository.
