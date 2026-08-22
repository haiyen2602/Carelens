# BUILD-6 — Tool Gateway + Core Domain Tools

Date: 2026-08-18  
Scope: strict read-only Tool Gateway for the disabled Agent V2 path. `AGENT_RUNTIME_ENABLED=false` remains unchanged. No write tool, RAG redesign, Doctor Handoff, long-term memory, migration, or legacy-chat behavior change was made.

## Tool Gateway

`backend/agents/v2/tools.py` now defines the complete six-tool `ToolName` enum and a closed `_TOOL_DEFINITIONS` registry. Dynamic method dispatch and direct ORM/SQL imports were removed from the Agent package.

Every tool call is required to pass a Pydantic input schema with `extra="forbid"`; every domain projection is independently checked against a typed output schema before it can return to the Agent runtime. Only this allowlist exists:

```text
search_drug
get_drug_info
get_active_prescriptions
get_today_doses
get_upcoming_doses
get_dose_status
```

Any other name, missing/invalid field, over-limit catalog query, or attempted `patient_id` injection fails before a domain read with a stable safe code (`TOOL_NOT_ALLOWED` or `INVALID_TOOL_ARGUMENTS`). Domain, ORM, and infrastructure exceptions are converted to `TOOL_UNAVAILABLE`; raw SQL, stack traces, and patient data are not exposed to the model.

## Domain boundary and authorization

`backend/services/agent_read_only_tools.py` is the server-side read adapter. It calls the actual domain-owned Drug Knowledge V2 facade, `Prescription` read model, and V2 Scheduling runtime adapter. `backend/services/agent_authorization.py` owns the relationship authorization query. Both return only server-validated values to the Agent boundary; `backend/agents/v2` has no direct ORM/SQL import.

The route still authorizes the actor/patient pair through `require_agent_patient_access` before creating an `AuthorizedToolContext`:

```text
JWT actor → relationship authorization → AuthorizedToolContext
          → Tool Gateway → domain read adapter
```

The authenticated `patient_id` is retained only in that server-created context. Tool schemas do not have a patient-ID field, so a model cannot override scope. The scheduling adapter checks the resolved opaque dose group against the same authorized patient; cross-patient IDs return the same safe unavailable result and do not disclose their existence.

## Tool sources and metadata

| Tool | Domain adapter/source | Authority | Provenance |
| --- | --- | --- | --- |
| `search_drug` | Canonical Drug Knowledge V2 catalog | `DRUG_KNOWLEDGE_V2` | `canonical-drug-v2:catalog` |
| `get_drug_info` | Canonical Drug Knowledge V2 retrieval | `DRUG_KNOWLEDGE_V2` | `canonical-drug-v2:knowledge` |
| `get_active_prescriptions` | Operational Prescription read model | `OPERATIONAL_DB` | `operational-db:prescription:active` |
| `get_today_doses` | V2 Scheduling grouped-dose projection | `OPERATIONAL_DB` | `operational-db:dose-occurrence:today` |
| `get_upcoming_doses` | V2 Scheduling grouped-dose projection | `OPERATIONAL_DB` | `operational-db:dose-occurrence:upcoming` |
| `get_dose_status` | V2 Scheduling grouped-dose projection | `OPERATIONAL_DB` | `operational-db:dose-occurrence:status` |

Each `ToolResult` includes server-produced freshness and can be converted into BUILD-4 `TOOL` context. Drug V2 and Operational DB authorities remain protected in Context Manager. A short-term user claim or resolved memory reference therefore cannot replace an authoritative dose, prescription, safety, or drug lookup; it can only prompt a fresh approved tool read.

## Guardrails

BUILD-3 already owns the runtime execution limits. The Tool Gateway is the one gateway supplied to `ReadOnlyAgentRuntime`, so its strict allowlist/schema gate is applied before each domain call, while the runtime continues to enforce model-plan tool-call budget and duplicate-signature loop detection before any tool executes.

No write capability is represented in the registry or exposed by the route.

## Validation

```text
# Actual local read smoke (Canonical V2 + local PostgreSQL read path)
AgentReadOnlyDomainTools.search_drug("Amlodipine Stada 10mg TAB 10x14", 1)
AgentReadOnlyDomainTools.get_drug_info(<resolved legacy id>, "cong dung")
AgentReadOnlyDomainTools.get_active_prescriptions("agent-build-6-no-access")
AgentReadOnlyDomainTools.get_today_doses("agent-build-6-no-access")
AgentReadOnlyDomainTools.get_upcoming_doses("agent-build-6-no-access")
DOMAIN_READ_SMOKE_PASS

pytest -q tests/test_agent_v2_tools.py tests/test_agent_v2_short_term_memory.py \
  tests/test_agent_v2_context.py tests/test_agent_v2_runtime.py \
  tests/test_agent_v2_model_gateway.py tests/test_agent_v2_route.py \
  tests/test_chat_security_gate.py tests/test_chat_routes.py \
  tests/services/scheduling/test_runtime_adapter.py \
  tests/services/drug_knowledge/test_v2_catalog.py
63 passed

ruff check backend/agents/v2 backend/services/agent_authorization.py \
  backend/services/agent_read_only_tools.py \
  backend/api/agent_v2_routes.py tests/test_agent_v2_tools.py \
  tests/test_agent_v2_short_term_memory.py tests/test_agent_v2_context.py \
  tests/test_agent_v2_runtime.py tests/test_agent_v2_model_gateway.py \
  tests/test_agent_v2_route.py
PASS

python -m compileall -q backend/agents/v2 backend/services/agent_authorization.py \
  backend/services/agent_read_only_tools.py \
  backend/api/agent_v2_routes.py
PASS

git diff --check
PASS
```

Tests cover all six real typed contracts, strict allowlist, invalid input, output validation, safe error sanitation, server-owned patient scope, denied cross-patient opaque dose access, Tool Context provenance/authority/freshness, memory non-override behavior, BUILD-3 tool budget/loop regression, Agent V2 feature flag behavior, legacy chat security/routes, scheduling adapter, and Drug V2 catalog regression.

## P1 deferred by scope

- Tool-result persistence/audit event storage and end-user provenance rendering await later Agent observability/response-composer work.
- The current disabled route has no production model/tool continuation loop; BUILD-6 validates the boundary that the later runtime will use.
- No Safety Domain tool is available until the dedicated Safety Integration build.

## Conclusion

BUILD-6: PASS

TOOL GATEWAY: PASS

DOMAIN TOOLS: PASS

AUTHORIZATION: PASS

PROVENANCE/AUTHORITY: PASS

GUARDRAILS: PASS

REGRESSION: PASS

READY FOR BUILD-7: YES
