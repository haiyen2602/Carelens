export type StoredChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  at: string;
  // BUILD-29: chi gan cho tin nhan role="assistant" - trace_id/agent_run_id
  // la nhung gi response /api/chat THAT SU da tra ve cho dung luot nay (xem
  // frontend/src/app/api/chat/route.ts's adaptAgentV2Response), luu lai o
  // day de nut "Báo cáo câu trả lời" khong bao gio phai boi nguoi dung nhap
  // tay trace/session id. userMessage la cau hoi cua chinh nguoi dung ngay
  // truoc luot tra loi nay (khong doc tu message lien ke trong mang, tranh
  // sai lech neu lich su bi chinh sua sau nay).
  traceId?: string;
  agentRunId?: string;
  userMessage?: string;
  suggestedActions?: import("@/types/chat").SuggestedAction[];
  drugImage?: {
    attemptId: string;
    outcome: string | null;
    candidates: import("@/types/chat").DrugImageCandidate[];
  };
  imageAttachment?: {
    fileName: string;
    // A Blob/Object URL is intentionally in-memory only. It is not a durable
    // image store and never contains base64/binary image data.
    previewUrl?: string;
  };
};

export type Conversation = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: StoredChatMessage[];
};

const CONVERSATIONS_KEY = "capymedi_patient_chat_conversations";
const ACTIVE_KEY = "capymedi_patient_chat_active_id";

export function loadConversations(): Conversation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(CONVERSATIONS_KEY);
    return raw ? (JSON.parse(raw) as Conversation[]) : [];
  } catch {
    return [];
  }
}

export function saveConversations(conversations: Conversation[]) {
  if (typeof window === "undefined") return;
  // Blob URLs die at page unload. Persist only a filename, never bytes, a
  // base64 payload, or a stale object URL that might be mistaken for a real
  // server-side attachment after reload.
  const serializable = conversations.map((conversation) => ({
    ...conversation,
    messages: conversation.messages.map((message) =>
      message.imageAttachment
        ? { ...message, imageAttachment: { fileName: message.imageAttachment.fileName } }
        : message,
    ),
  }));
  window.localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(serializable));
}

export function loadActiveId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE_KEY);
}

export function saveActiveId(id: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACTIVE_KEY, id);
}

export function createConversation(): Conversation {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    title: "Hội thoại mới",
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

export function titleFromMessage(content: string) {
  const trimmed = content.trim().replace(/\s+/g, " ");
  if (!trimmed) return "Hội thoại mới";
  return trimmed.length > 40 ? `${trimmed.slice(0, 40)}…` : trimmed;
}

export function formatConversationTime(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatMessageTime(iso: string) {
  return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}
