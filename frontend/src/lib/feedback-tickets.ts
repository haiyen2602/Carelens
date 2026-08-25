// BUILD-29: Admin "Báo cáo chatbot / User Reports" ticket explorer -- calls
// the backend directly with a Bearer token (same pattern as
// frontend/src/app/admin/rag/page.tsx), not through a Next.js proxy route
// (that pattern is reserved for the patient-facing chat/feedback submit
// path -- see app/api/chat/route.ts and app/api/feedback/route.ts).

export type FeedbackTicketReason =
  | "WRONG_ANSWER"
  | "NOT_UNDERSTOOD"
  | "WRONG_MEDICATION_INFO"
  | "UNSAFE_OR_INAPPROPRIATE"
  | "TECHNICAL_ERROR"
  | "OTHER";

export type FeedbackTicketStatus = "OPEN" | "INVESTIGATING" | "FIXED" | "CLOSED" | "WONT_FIX";
export type FeedbackTicketPriority = "P0" | "P1" | "P2" | "P3";

export type FeedbackTicket = {
  id: string;
  actor_id: string;
  patient_id: string;
  conversation_id: string;
  trace_id: string | null;
  agent_run_id: string;
  user_message: string;
  assistant_message: string;
  reason: FeedbackTicketReason;
  user_note: string | null;
  chatbot_version: string;
  status: FeedbackTicketStatus;
  priority: FeedbackTicketPriority;
  p0_review_required: boolean;
  admin_note: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
};

export type FeedbackTicketList = {
  items: FeedbackTicket[];
  total: number;
  limit: number;
  offset: number;
};

export type FeedbackTraceSummary = {
  trace_id: string;
  found: boolean;
  intent: string | null;
  tools: string[];
  tool_results: { name: string; output: unknown }[];
  safety_outcome: string | null;
  handoff_created: boolean;
  model: string | null;
  latency_ms: number | null;
  scores: Record<string, number | string | boolean>;
  final_response: string | null;
  status: string | null;
};

// BUILD-33/36: backend already returns these on GET /admin/tickets/{id}
// (agent_feedback.judge_result_out/evaluation_result_out/safety_result_out)
// -- the frontend type previously didn't even declare `judge`, so it was
// silently dropped by every caller despite the backend already computing
// it (see BUILD-36 report's own audit finding).
export type FeedbackJudgeResult = {
  judge_status: string;
  judge_provider: string;
  judge_model: string;
  rubric_name: string;
  rubric_version: string;
  judge_prompt_version: string;
  eligibility_reason: string;
  overall_score: number | null;
  dimension_scores: Record<string, number>;
  flags: string[];
  confidence: number | null;
  failure_reason: string | null;
  evaluated_at: string | null;
};

export type FeedbackEvaluationResult = {
  evaluation_version: string;
  execution_path: string | null;
  metrics: Record<string, unknown>;
};

export type FeedbackSafetyResult = {
  outcome: string;
  reason_code: string;
  severity: string;
  handoff_required: boolean;
  handoff_created: boolean;
  handoff_id: string | null;
  handoff_status_live: string | null;
  handoff_resolved: boolean;
  assigned_doctor_id: string | null;
  time_to_review_seconds: number | null;
};

export type FeedbackTicketDetail = {
  ticket: FeedbackTicket;
  trace: FeedbackTraceSummary;
  judge: FeedbackJudgeResult | null;
  evaluation: FeedbackEvaluationResult | null;
  safety: FeedbackSafetyResult | null;
};

export type FeedbackSessionMessage = {
  trace_id: string;
  timestamp: string;
  query_preview: string;
  final_answer_preview: string;
  status: string;
  is_reported_turn: boolean;
};

export type FeedbackSession = {
  conversation_id: string;
  items: FeedbackSessionMessage[];
  total: number;
  limit: number;
  offset: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function authHeaders(accessToken?: string | null): HeadersInit | undefined {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined;
}

async function parseOrThrow<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `${fallback} (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export async function listFeedbackTickets(
  options: {
    status?: string;
    priority?: string;
    reason?: string;
    chatbotVersion?: string;
    dateFrom?: string;
    dateTo?: string;
    limit?: number;
    offset?: number;
    accessToken?: string | null;
    signal?: AbortSignal;
  } = {},
): Promise<FeedbackTicketList> {
  const params = new URLSearchParams();
  if (options.status && options.status !== "all") params.set("status", options.status);
  if (options.priority && options.priority !== "all") params.set("priority", options.priority);
  if (options.reason && options.reason !== "all") params.set("reason", options.reason);
  if (options.chatbotVersion && options.chatbotVersion !== "all")
    params.set("chatbot_version", options.chatbotVersion);
  if (options.dateFrom) params.set("date_from", options.dateFrom);
  if (options.dateTo) params.set("date_to", options.dateTo);
  params.set("limit", String(options.limit ?? 50));
  params.set("offset", String(options.offset ?? 0));

  const response = await fetch(`${API_BASE}/api/v1/admin/tickets?${params}`, {
    signal: options.signal,
    headers: authHeaders(options.accessToken),
  });
  return parseOrThrow(response, "Không thể tải danh sách báo cáo");
}

export async function getFeedbackTicket(
  ticketId: string,
  accessToken?: string | null,
): Promise<FeedbackTicketDetail> {
  const response = await fetch(`${API_BASE}/api/v1/admin/tickets/${encodeURIComponent(ticketId)}`, {
    headers: authHeaders(accessToken),
  });
  return parseOrThrow(response, "Không thể tải chi tiết báo cáo");
}

export async function getFeedbackTicketSession(
  ticketId: string,
  options: { limit?: number; offset?: number; accessToken?: string | null } = {},
): Promise<FeedbackSession> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
  });
  const response = await fetch(
    `${API_BASE}/api/v1/admin/tickets/${encodeURIComponent(ticketId)}/session?${params}`,
    {
      headers: authHeaders(options.accessToken),
    },
  );
  return parseOrThrow(response, "Không thể tải phiên hội thoại");
}

export async function updateFeedbackTicket(
  ticketId: string,
  payload: {
    status?: FeedbackTicketStatus;
    priority?: FeedbackTicketPriority;
    admin_note?: string;
  },
  accessToken?: string | null,
): Promise<FeedbackTicket> {
  const response = await fetch(`${API_BASE}/api/v1/admin/tickets/${encodeURIComponent(ticketId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders(accessToken) },
    body: JSON.stringify(payload),
  });
  return parseOrThrow(response, "Không thể cập nhật báo cáo");
}
