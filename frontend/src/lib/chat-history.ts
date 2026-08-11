export type StoredChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  at: string;
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
  window.localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
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
