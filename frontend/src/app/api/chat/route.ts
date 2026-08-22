// Server-side proxy cho chat that. BUILD-26: doi target tu backend
// `/api/v1/chat` (legacy) sang `/api/v1/agent/v2/orchestrate` (Agent V2,
// da validated qua BUILD-24O..25B) - day la con duong DUY NHAT frontend
// dung de gui chat that (xac nhan qua audit BUILD-26 -- xem
// data pharmacy/reports/agent-architecture/56-build-26-*.md).
//
// TASK-010 (2026-08-13): forward nguyen header `Authorization` tu client
// (trinh duyet, qua useAuth() - xem frontend/src/lib/auth.tsx) sang backend,
// KHONG tu gan X-Internal-Secret. Backend tu tra 401/403 neu thieu/sai/het
// han JWT hoac sai patient scoping - route nay khong tu kiem tra truoc.
//
// Van giu route proxy nay (khong goi thang backend tu client) - cung ly do
// nhu truoc: de doi sang forward qua httpOnly cookie/refresh-on-401 ma
// khong dong vao component goi chat, xem cung pattern o frontend/src/app/api/auth/*.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// BUILD-26 feature flag, per instruction: CHAT_RUNTIME=v2|legacy, mac dinh
// production la v2. Day la duong rollback khan cap KHONG can sua code/deploy
// lai - chi doi env var nay ve "legacy" va restart. KHONG dung de tu dong
// fallback am tham tu v2 sang legacy khi v2 loi (xem nhanh loi ben duoi -
// mot request that bai o v2 tra ve loi that, khong bao gio thu lai o legacy).
const CHAT_RUNTIME = (process.env.CHAT_RUNTIME ?? "v2").toLowerCase();

type AgentV2Citation = { title: string; source: string; url: string | null };
type AgentV2SuggestedAction = {
  action_id: string;
  type: "drug_attribute" | "topic_attribute";
  label: string;
  value: string;
  entity_id?: string;
  topic?: string;
};

type AgentV2OrchestrateResponse = {
  status: string;
  reply: string;
  intent: string;
  tools: string[];
  citations: AgentV2Citation[];
  safety_disposition: string | null;
  handoff_id: string | null;
  trace_id: string;
  agent_run_id: string;
  suggested_actions: AgentV2SuggestedAction[];
};

// BUILD-26 adapter -- maps Agent V2's real response shape onto the UI's
// existing ChatResponse contract, per the integration instruction: "Khong
// sua Agent V2 chi de ep no giong Legacy neu co the map o proxy layer."
// Fields with no honest v2 equivalent (classification, needs_clarification,
// sources) get explicit, documented defaults -- never a fabricated mapping.
function adaptAgentV2Response(v2: AgentV2OrchestrateResponse) {
  // Agent V2's own reason-code-aware fixed messages (backend/agents/v2/runtime.py
  // ::_safety_blocked_message / _handoff_required_message / _handoff_created_message,
  // and the plain fixed strings for FAILED/TIMEOUT/BUDGET_EXCEEDED/CANCELLED)
  // are ALWAYS a complete, safe, Vietnamese, user-facing sentence in `reply`
  // for every status value -- so the chat UI can keep rendering `reply`
  // exactly as it already does today (frontend/src/app/patient/assistant/page.tsx
  // only ever reads `data.reply`) with no special per-status branch needed,
  // and never needs to fall back to a generic/legacy message.
  const escalated = v2.safety_disposition != null && v2.safety_disposition !== "SAFE";
  return {
    reply: v2.reply,
    classification: null,
    severity: escalated ? "HIGH" : null,
    safety_flag: escalated,
    needs_clarification: false,
    sources: [],
    status: v2.status,
    citations: v2.citations,
    safety_disposition: v2.safety_disposition,
    handoff_id: v2.handoff_id,
    trace_id: v2.trace_id,
    agent_run_id: v2.agent_run_id,
    chatbot_version: "agent-v2" as const,
    suggested_actions: v2.suggested_actions ?? [],
  };
}

export async function POST(request: Request) {
  const body = await request.text();
  const authorization = request.headers.get("authorization");

  if (CHAT_RUNTIME === "legacy") {
    // Rollback path -- unchanged legacy proxy, kept intact per instruction
    // ("giu Legacy code/endpoint ton tai de rollback khan cap").
    const upstream = await fetch(`${BACKEND_URL}/api/v1/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authorization ? { Authorization: authorization } : {}),
      },
      body,
    });
    const data = await upstream.text();
    return new Response(data, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Default production path: Agent V2. The incoming body already carries
  // patient_id/message/dose_id/conversation_id under the SAME field names
  // AgentV2OrchestrateRequest expects (see frontend/src/types/chat.ts) --
  // forwarded as-is, no request-shape transform needed.
  const upstream = await fetch(`${BACKEND_URL}/api/v1/agent/v2/orchestrate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(authorization ? { Authorization: authorization } : {}),
    },
    body,
  });

  if (!upstream.ok) {
    // Real error, forwarded as-is -- 403 (cross-patient/auth), 404 (not
    // admitted by rollout/allowlist), 409 (idempotency conflict), 503
    // (commit failure), etc. all carry Agent V2's own real `detail` message
    // through unchanged. No silent retry against legacy on any failure.
    const errorBody = await upstream.text();
    return new Response(errorBody, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  const v2Data = (await upstream.json()) as AgentV2OrchestrateResponse;
  return new Response(JSON.stringify(adaptAgentV2Response(v2Data)), {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
