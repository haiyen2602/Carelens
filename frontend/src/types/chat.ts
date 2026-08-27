// BUILD-26: this UI-facing contract now maps onto Agent V2's
// AgentV2OrchestrateResponse (backend/models/schemas.py) via the adapter in
// frontend/src/app/api/chat/route.ts, not directly onto the legacy
// ConversationChatResponse anymore -- see that route's own comment for the
// exact field-by-field mapping. Kept the original field names/shapes
// (classification/severity/safety_flag/needs_clarification/sources) so
// this type change doesn't force a rendering change in any component that
// only reads `reply` (the only field frontend/src/app/patient/assistant/page.tsx
// actually consumes today) -- Agent V2 has no direct equivalent for most of
// these, so the adapter fills them with honest defaults (null/false/[])
// rather than fabricating a mapping that doesn't really exist. The new
// fields below carry Agent V2's own real data for anything that wants it.

export type ChatRequest = {
  patient_id: string;
  message: string;
  dose_id?: string;
  // BUILD-26: threads this message into the same Agent V2 conversation/
  // short-term-memory scope as the rest of this UI thread -- pass the
  // conversation's own stable id (see frontend/src/lib/chat-history.ts),
  // not a new one per message.
  conversation_id?: string;
  selected_action?: SelectedAction;
};

export type DrugImageCandidate = {
  action_id: string;
  product_display_name: string;
  strength_text: string | null;
  rank: number;
};

export type DrugImageRecognitionResponse = {
  status:
    | "CANDIDATES"
    | "INSUFFICIENT_EVIDENCE"
    | "SAFETY_DEFERRED"
    | "DOCTOR_ACTIVE"
    | "RECOGNITION_UNAVAILABLE";
  reply: string;
  recognition_attempt_id: string | null;
  outcome: string | null;
  recognition_version: string | null;
  candidates: DrugImageCandidate[];
  requested_attribute: string | null;
};

export type DrugImageConfirmResponse = {
  status: "CONFIRMED";
  reply: string;
  recognition_attempt_id: string;
  canonical_drug_product_id: string;
  requested_attribute: string | null;
  tools: string[];
};

export type SuggestedAction = {
  action_id: string;
  type: "topic_followup" | "drug_followup" | "schedule_followup";
  label: string;
  value: string;
  entity_id?: string;
  topic?: string;
};

export type SelectedAction = Omit<SuggestedAction, "label">;

export type ClassificationOut = {
  label: string; // TAKEN | MISSED | DELAYED | SIDE_EFFECT
  secondary_labels: string[];
};

export type SourceOut = {
  drug_id: string;
  field: string; // field_group: cong_dung | tac_dung_phu | cach_dung | bao_quan
};

export type CitationOut = {
  title: string;
  source: string;
  url: string | null;
};

export type ChatResponse = {
  reply: string;
  // BUILD-26: Agent V2 has no direct equivalent (its own `intent` enum is a
  // different concept, not the TAKEN/MISSED/DELAYED/SIDE_EFFECT dose
  // classification this field originally meant) -- always null from the
  // v2 adapter, not a fabricated mapping.
  classification: ClassificationOut | null;
  // BUILD-26: best-effort derived from Agent V2's real safety_disposition
  // (see route.ts) rather than a legacy-only concept with no v2 source.
  severity: string | null; // LOW | MEDIUM | HIGH
  safety_flag: boolean;
  // BUILD-26: no direct v2 signal for this yet -- always false, not guessed.
  needs_clarification: boolean;
  // BUILD-26: legacy's drug_id/field shape doesn't fit Agent V2's citations
  // (title/source/url) -- always [] here; use the new `citations` field
  // below for Agent V2's real citation data instead of forcing a bad fit.
  sources: SourceOut[];
  // --- New, Agent V2-specific fields (optional: older code that only reads
  // the fields above keeps working unmodified) ---
  status?: string; // COMPLETED | HANDOFF_CREATED | SAFETY_BLOCKED | HANDOFF_REQUIRED | FAILED | TIMEOUT | BUDGET_EXCEEDED | CANCELLED
  citations?: CitationOut[];
  safety_disposition?: string | null;
  handoff_id?: string | null;
  trace_id?: string;
  agent_run_id?: string;
  chatbot_version?: "agent-v2" | "legacy";
  suggested_actions?: SuggestedAction[];
};

export type AgentStatus = {
  status: string;
  agent: string;
};

// Local-only shape dung de luu lich su hoi thoai trong UI (khong gui len backend
// nguyen vec — xem chat-history.ts).
export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

// BUILD-29: 6 ly do co dinh trong nut "Báo cáo câu trả lời" (khop
// AgentFeedbackReason o backend/models/schemas.py) - khong phai free-text,
// de server phan loai priority mot cach xac dinh (khong doan qua NLP).
export type FeedbackReason =
  | "WRONG_ANSWER"
  | "NOT_UNDERSTOOD"
  | "WRONG_MEDICATION_INFO"
  | "UNSAFE_OR_INAPPROPRIATE"
  | "TECHNICAL_ERROR"
  | "OTHER";

export type FeedbackReportRequest = {
  conversation_id: string;
  trace_id: string | null;
  agent_run_id: string;
  user_message: string;
  assistant_message: string;
  reason: FeedbackReason;
  user_note?: string | null;
};

export type FeedbackReportResponse = {
  id: string;
  status: string;
  priority: string;
};

// BUILD-30: "Xem hoạt động" - timeline patient-safe, xay tu trace THAT cua
// dung message do (khong bao gio hardcode). Khop
// backend/models/schemas.py::AgentActivityItemOut/AgentActivityOut.
export type ActivityItem = {
  type: string;
  label: string;
  status: string;
  duration_ms: number | null;
  source_count?: number | null;
};

export type ActivityResponse = {
  trace_id: string;
  available: boolean;
  activities: ActivityItem[];
};
