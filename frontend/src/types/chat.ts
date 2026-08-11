// Mirrors backend/models/schemas.py (ConversationChatRequest / ConversationChatResponse)
// on the backend — POST /api/v1/chat, xem api-contracts.md §4. Giu dung ten field,
// KHONG doi tuy tien o day ma khong doi ca 2 phia (se pha contract).

export type ChatRequest = {
  patient_id: string;
  message: string;
  dose_id?: string;
};

export type ClassificationOut = {
  label: string; // TAKEN | MISSED | DELAYED | SIDE_EFFECT
  secondary_labels: string[];
};

export type SourceOut = {
  drug_id: string;
  field: string; // field_group: cong_dung | tac_dung_phu | cach_dung | bao_quan
};

export type ChatResponse = {
  reply: string;
  classification: ClassificationOut | null;
  severity: string | null; // LOW | MEDIUM | HIGH
  safety_flag: boolean;
  needs_clarification: boolean;
  sources: SourceOut[];
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
