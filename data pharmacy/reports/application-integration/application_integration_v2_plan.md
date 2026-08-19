# Application Integration V2 Plan

## 1. Status and purpose

Database Architecture V2 is complete through DB-4I. The next phase is
**Application Integration V2**.

The purpose of this phase is to connect the already validated V2 data,
database schema, and domain services to the real local application
runtime, while preserving a safe legacy fallback and avoiding premature
production cutover.

This phase is **not** a Railway deployment phase and is **not** an
Agent/LLM integration phase.

------------------------------------------------------------------------

## 2. Primary objective

Prove locally that the real application can use the V2 domain safely
from end to end:

``` text
Doctor UI
   |
   v
Drug Identity V2
   |
   v
Prescription V2
   |
   v
Medication Plan
   |
   v
Schedule Rule / Time / Cycle
   |
   v
Dose Occurrence
   |
   v
Dose State
   |
   v
Safety Assessment
   |
   v
Escalation Decision
```

The application should consume the audited V2 domain boundaries instead
of writing directly to V2 tables or reimplementing medical/scheduling
rules in API/UI code.

------------------------------------------------------------------------

## 3. Guiding principles

1.  **Local first**
    -   All integration and validation must be completed locally before
        Railway deployment is considered.
2.  **Incremental cutover**
    -   Integrate one runtime flow at a time.
    -   Do not switch the whole application to V2 in one change.
3.  **Keep legacy available**
    -   Existing runtime behavior must remain available until the
        corresponding V2 path passes its integration gates.
4.  **Domain services are the boundary**
    -   API/UI code must call the approved V2 services.
    -   Do not directly mutate scheduling, occurrence, safety, or
        escalation tables from controllers/routes.
5.  **Fail closed**
    -   Ambiguous drug identity, invalid schedule, unknown policy, or
        unsafe provenance must not be guessed.
6.  **Idempotency and transaction safety**
    -   Retries must not create duplicate prescriptions, schedules,
        occurrences, events, assessments, or notification jobs.
7.  **No clinical inference in UI or Agent**
    -   Safety level and escalation decisions come from the audited
        Safety Policy domain.
8.  **No production activation during this phase**
    -   No Railway cutover.
    -   No real notification-provider delivery.
    -   No production scheduler.
    -   No Agent clinical behavior.

------------------------------------------------------------------------

## 4. Existing V2 foundations

Application Integration may rely on the completed Database Architecture
boundaries:

-   canonical Drug Identity V2;
-   `drug_id_map`;
-   `prescription_item`;
-   `medication_plan`;
-   `schedule_rule`;
-   `schedule_rule_time`;
-   `schedule_rule_cycle`;
-   `dose_occurrence`;
-   `dose_event_log`;
-   `notification_job`;
-   `medication_safety_policy`;
-   `missed_dose_assessment`;
-   `safety_event`;
-   doctor prescription write path;
-   bounded dose occurrence generator;
-   dose state machine;
-   reminder/outbox domain;
-   safety policy resolver;
-   safety escalation decision boundary.

Current Alembic head at phase start: `0027`.

------------------------------------------------------------------------

# 5. Work plan

## APP-1 - Runtime Audit

### Goal

Understand exactly how the current application works before changing
runtime behavior.

### Work

Audit backend APIs, services, frontend calls, and relevant runtime paths
for:

-   drug search/select;
-   doctor prescription create/edit/approve;
-   prescription read/display;
-   dose schedule/list;
-   taken/delayed/missed/skipped actions;
-   reminder-related runtime;
-   caregiver/clinician flows;
-   safety/escalation flows;
-   chatbot/personal medication tools if currently connected;
-   legacy tables/services touched by each path.

Create a mapping:

``` text
Current UI/API
    ->
Current legacy service/table
    ->
Available V2 service
    ->
Integration/cutover risk
```

Identify:

-   direct DB writes;
-   duplicate business logic;
-   hidden legacy dependencies;
-   API contracts that must remain compatible;
-   authentication/authorization dependencies;
-   transaction boundaries;
-   places where V2 can initially run in shadow mode.

### Do not

-   modify runtime behavior;
-   cut over any endpoint;
-   deploy Railway.

### Output

`data pharmacy/reports/application-integration/01-runtime-audit.md`

### Gate

`READY FOR INTEGRATION DESIGN: YES/NO`

------------------------------------------------------------------------

## APP-2 - V2 Integration Design

### Goal

Define how V2 is introduced without unsafe big-bang replacement.

### Design

Use explicit runtime modes where appropriate:

``` text
LEGACY
SHADOW
V2_PRIMARY
V2_WITH_LEGACY_FALLBACK
```

Define per flow:

-   read source;
-   write source;
-   shadow comparison behavior;
-   compatibility DTO/adapter;
-   feature flag;
-   rollback mechanism;
-   audit/logging;
-   error/fail-closed behavior.

Do not introduce dual-write unless there is a clear requirement and
deterministic reconciliation strategy.

### Required decisions

-   Which endpoint is integrated first?
-   Which legacy API contracts must remain unchanged?
-   How is V1/V2 mismatch recorded?
-   What qualifies a flow to move from SHADOW to V2_PRIMARY?
-   How is rollback performed without data loss?

### Output

`data pharmacy/reports/application-integration/02-v2-integration-design.md`

### Gate

`READY FOR DOCTOR PRESCRIPTION INTEGRATION: YES/NO`

------------------------------------------------------------------------

## APP-3 - Doctor Prescription Runtime Integration

### Goal

Connect the real doctor prescription form/API to the validated V2 write
path.

### Target flow

``` text
Doctor selects patient
        |
Doctor selects Drug Identity V2
        |
dose / frequency / meal / times / dates / cycle
        |
V2 write-path validation
        |
prescription_item
        |
medication_plan
        |
schedule_rule
        +-- schedule_rule_time
        +-- schedule_rule_cycle
```

### Validate

-   correct drug identity;
-   dose text;
-   doses per day;
-   meal instruction;
-   times of day;
-   inclusive start/end dates;
-   optional cycle;
-   edit/retry behavior;
-   invalid inputs;
-   ambiguous drug identity;
-   transaction rollback;
-   API compatibility;
-   authorization.

Uncertain data must remain `REVIEW_REQUIRED`; the runtime must not
invent schedule or drug mappings.

### Output

`data pharmacy/reports/application-integration/03-doctor-prescription-runtime.md`

### Gate

`READY FOR DOSE RUNTIME INTEGRATION: YES/NO`

------------------------------------------------------------------------

## APP-4 - Dose and Schedule Runtime Integration

### Goal

Connect active V2 medication plans to the application's dose runtime.

### Target flow

``` text
ACTIVE medication plan
        |
bounded occurrence generation
        |
dose_occurrence
        |
patient dose list
        |
SCHEDULED -> DUE -> TAKEN / DELAYED / MISSED / SKIPPED
        |
dose_event_log
```

### Requirements

-   one occurrence = one drug at one intended time;
-   UI may visually group medicines with the same time;
-   local date/time/timezone must remain correct;
-   occurrence generation must always use a finite window;
-   reruns must create zero duplicates;
-   state transitions must use the existing audited domain service;
-   invalid transitions must be rejected;
-   concurrency must remain safe.

### Output

`data pharmacy/reports/application-integration/04-dose-runtime.md`

### Gate

`READY FOR SAFETY RUNTIME INTEGRATION: YES/NO`

------------------------------------------------------------------------

## APP-5 - Safety Runtime Integration

### Goal

Connect real V2 dose-state events to the audited safety boundary.

### Target flow

``` text
MISSED / DELAYED
      |
Safety Policy Resolver
      |
missed_dose_assessment
      |
safety_event
      |
Escalation Decision
      |
notification_job (outbox only)
```

### Requirements

-   runtime must not calculate risk independently;
-   resolver order remains:
    `DRUG_PRODUCT -> INGREDIENT -> CATEGORY -> SYSTEM_DEFAULT`;
-   unknown/ambiguous cases fail closed;
-   legacy category fallback remains unreviewed and cannot become
    automatic clinical advice;
-   automatic escalation requires approved reviewed provenance;
-   no real provider notification is sent in this task.

### Output

`data pharmacy/reports/application-integration/05-safety-runtime.md`

### Gate

`READY FOR SHADOW VALIDATION: YES/NO`

------------------------------------------------------------------------

## APP-6 - Shadow and Compatibility Validation

### Goal

Compare V1 and V2 behavior before V2 becomes the primary runtime.

Where meaningful:

``` text
Real local request
   |             |
   v             v
 Legacy        V2 shadow
 result        result
   \             /
    \           /
       diff
```

The shadow result must not create duplicate user-visible side effects.

### Compare

-   drug identity;
-   prescription representation;
-   schedule/times;
-   dose list;
-   state;
-   safety outcome where comparable;
-   API response compatibility.

Classify differences:

-   EXPECTED_V2_CHANGE;
-   LEGACY_BUG;
-   V2_BUG;
-   DATA_MISMATCH;
-   REVIEW_REQUIRED.

### Output

`data pharmacy/reports/application-integration/06-shadow-compatibility.md`

### Gate

`READY FOR LOCAL E2E: YES/NO`

------------------------------------------------------------------------

## APP-7 - Local End-to-End Validation

### Goal

Validate the complete V2 application path using the real local app and
disposable/reproducible PostgreSQL.

### Primary E2E scenario

``` text
Doctor logs in
   ->
selects patient
   ->
searches/selects medicine
   ->
creates prescription
   ->
schedule is persisted
   ->
occurrences are generated
   ->
patient sees intended doses
   ->
dose becomes due
   ->
patient action or missed state
   ->
safety assessment
   ->
escalation decision/outbox
```

### Required scenarios

-   normal prescription;
-   multiple medicines at the same time;
-   multiple times per day;
-   inclusive end date;
-   open-ended plan with bounded generation;
-   cycle on/off;
-   invalid schedule;
-   ambiguous/unresolved drug;
-   retry/idempotency;
-   transaction rollback;
-   concurrent dose action;
-   missed dose with reviewed policy;
-   missed dose with legacy/unreviewed fallback;
-   unknown safety policy;
-   legacy compatibility/regression.

### Validation environment

-   local only;
-   clean/disposable PostgreSQL;
-   repository migrations;
-   manifest-verified canonical artifacts;
-   no patient data committed to Git;
-   no Railway.

### Output

`data pharmacy/reports/application-integration/07-local-e2e-validation.md`

### Gate

`APPLICATION V2 LOCAL E2E: PASS/FAIL`

------------------------------------------------------------------------

## APP-8 - Application Integration Closeout

### Goal

Close the phase and establish the next production/Agent boundary.

### Review

Summarize:

-   endpoints integrated;
-   V2-primary paths;
-   legacy paths still active;
-   feature flags;
-   rollback strategy;
-   E2E evidence;
-   unresolved P0/P1;
-   technical debt;
-   production blockers;
-   Agent prerequisites.

### Output

`data pharmacy/reports/application-integration/08-application-integration-closeout.md`

### Final status

``` text
APPLICATION INTEGRATION V2: COMPLETE / INCOMPLETE

P0:
P1:

DOCTOR PRESCRIPTION V2:
DOSE RUNTIME V2:
SAFETY RUNTIME V2:
LOCAL E2E:
LEGACY FALLBACK AVAILABLE:

READY FOR AGENT ARCHITECTURE: YES/NO
READY FOR PRODUCTION SCHEDULER: YES/NO
READY FOR RAILWAY DEPLOYMENT: YES/NO
```

------------------------------------------------------------------------

# 6. Explicitly out of scope

The following must not be silently added to this phase:

-   Agent/LLM integration;
-   LangSmith production tracing;
-   clinical reasoning by an Agent;
-   policy authoring by an Agent;
-   real caregiver/clinician recipient resolution;
-   real push/SMS/email notification provider;
-   production cron/scheduler activation;
-   Railway deployment;
-   production database cutover;
-   legacy table deletion;
-   legacy retirement;
-   destructive migrations.

If one of these becomes necessary to complete a task, stop and document
the dependency instead of expanding scope automatically.

------------------------------------------------------------------------

# 7. Safety boundaries

The application must never:

-   infer an unresolved drug identity;
-   invent a schedule from ambiguous data;
-   treat legacy category severity as reviewed clinical advice;
-   convert `UNKNOWN` into low risk;
-   bypass `REQUIRE_MEDICAL_REVIEW`;
-   allow frontend/controller code to override Safety Policy decisions;
-   send clinician/caregiver escalation from an unreviewed legacy
    fallback;
-   let notification delivery become the source of truth for dose state.

------------------------------------------------------------------------

# 8. Compatibility and rollback

Every runtime integration task must answer:

1.  What legacy behavior exists today?
2.  What V2 path replaces or shadows it?
3.  What data is written?
4.  Can the request be safely retried?
5.  How is mismatch detected?
6.  How is the V2 path disabled?
7.  What happens to already-written V2 rows after rollback?
8.  Does rollback preserve patient-visible correctness?

Feature flags must be preferred over destructive rollback.

------------------------------------------------------------------------

# 9. Testing strategy

Use layered validation:

``` text
Unit/domain tests
      |
Integration tests
      |
Clean PostgreSQL tests
      |
API tests
      |
Real local UI flow
      |
Shadow comparison
      |
Local E2E
```

Do not claim a runtime path PASS solely from unit tests.

For database-dependent gates, prefer disposable PostgreSQL with no
reused volume.

------------------------------------------------------------------------

# 10. Reporting rules

All reports for this phase belong under:

``` text
data pharmacy/reports/application-integration/
```

Each task report should include:

-   scope;
-   files/components reviewed or changed;
-   current behavior;
-   implemented behavior;
-   validation evidence;
-   compatibility impact;
-   P0/P1;
-   unresolved decisions;
-   explicit next gate.

Do not hide failed checks. Use `BLOCKED` or `FAIL` when a required
validation cannot be completed.

------------------------------------------------------------------------

# 11. Definition of phase completion

Application Integration V2 is complete only when:

-   the doctor prescription flow uses the approved V2 write boundary;
-   V2 schedules and dose occurrences are usable by the local app;
-   patient dose-state actions use the audited state machine;
-   MISSED/DELAYED events can reach the audited Safety Policy boundary;
-   escalation decisions remain provenance-gated and fail closed;
-   retries and concurrent operations do not create duplicates;
-   local E2E passes on reproducible PostgreSQL;
-   legacy fallback/rollback behavior is documented;
-   no unresolved P0 remains.

Completion of this phase does **not** itself authorize Railway
deployment, real notification delivery, or Agent clinical behavior.

------------------------------------------------------------------------

# 12. Planned next phases

After Application Integration V2 closes successfully, evaluate
separately:

``` text
Application Integration V2
        |
        +--> Production Scheduler & Notification Delivery
        |
        +--> Agent Architecture / Tool Integration
        |
        +--> Observability / LangSmith
        |
        +--> Full Release / Production Readiness
        |
        +--> Railway Deployment & Controlled Cutover
```

Each future phase must define and pass its own production and safety
gates.
