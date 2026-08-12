import type { AgentStatus, ChatRequest, ChatResponse } from "@/types/chat";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Chua co auth-api that (JWT dang nhap benh nhan - chatbot-rag-design.md muc
// 10 #10), nen chua co cach xac dinh dung `patient_id` cua nguoi dang mo app.
// Dung tam ID benh nhan demo da seed san o backend
// (scripts/seed_demo_patient.py::DEMO_PATIENT_ID) de chat chay duoc that qua
// data that, khong bia patient_id ngau nhien. Doi thanh gia tri tu session
// that ngay khi auth-api co.
export const DEMO_PATIENT_ID = "demo-patient-01";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail ?? `API error: ${response.status}`, response.status);
  }

  return response.json();
}

export async function sendChatMessage(
  payload: ChatRequest,
  accessToken?: string | null,
): Promise<ChatResponse> {
  // Goi qua route noi bo (`app/api/chat/route.ts`) - route noi bo CHI
  // forward nguyen header Authorization sang backend that (TASK-010,
  // khong con tu gan X-Internal-Secret nua, xem ghi chu chi tiet trong
  // route.ts). `accessToken`: lay tu useAuth() (frontend/src/lib/auth.tsx) -
  // optional vi luc chua dang nhap that (F5 truoc khi refresh xong) van goi
  // duoc, backend se tra 401 dung nhu thiet ke.
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail ?? `API error: ${response.status}`, response.status);
  }

  return response.json();
}

export function getAgentStatus(): Promise<AgentStatus> {
  return request<AgentStatus>("/api/v1/status");
}
