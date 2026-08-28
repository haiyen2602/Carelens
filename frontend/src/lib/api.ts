import type {
  ActivityResponse,
  AgentStatus,
  ChatRequest,
  ChatResponse,
  FeedbackReportRequest,
  FeedbackReportResponse,
  DrugImageConfirmResponse,
  DrugImageRecognitionResponse,
} from "@/types/chat";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

export async function recognizeDrugImage(
  payload: { patientId: string; conversationId: string; message: string; file: File },
  accessToken?: string | null,
): Promise<DrugImageRecognitionResponse> {
  const form = new FormData();
  form.set("patient_id", payload.patientId);
  form.set("conversation_id", payload.conversationId);
  form.set("message", payload.message);
  form.set("file", payload.file);
  const response = await fetch("/api/drug-images/recognize", {
    method: "POST",
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new ApiError(
      typeof detail === "object" ? detail.message : (detail ?? `API error: ${response.status}`),
      response.status,
    );
  }
  return response.json();
}

export async function confirmDrugImageCandidate(
  payload: {
    patientId: string;
    conversationId: string;
    attemptId: string;
    actionId: string;
    decision?: "CONFIRMED" | "REJECTED";
  },
  accessToken?: string | null,
): Promise<DrugImageConfirmResponse> {
  const response = await fetch("/api/drug-images/confirm", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({
      patient_id: payload.patientId,
      conversation_id: payload.conversationId,
      recognition_attempt_id: payload.attemptId,
      action_id: payload.actionId,
      decision: payload.decision ?? "CONFIRMED",
    }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new ApiError(
      typeof detail === "object" ? detail.message : (detail ?? `API error: ${response.status}`),
      response.status,
    );
  }
  return response.json();
}

export function getAgentStatus(): Promise<AgentStatus> {
  return request<AgentStatus>("/api/v1/status");
}

// BUILD-30: goi qua route noi bo (`app/api/activity/[traceId]/route.ts`),
// cung mau voi submitFeedbackReport o tren. Khong throw tren 403/khong tim
// thay - component tu quyet dinh hien thi trang thai gi (unavailable/error)
// tu chinh response, khong dua vao exception.
export async function getTraceActivity(
  traceId: string,
  accessToken?: string | null,
): Promise<ActivityResponse> {
  const response = await fetch(`/api/activity/${encodeURIComponent(traceId)}`, {
    headers: {
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail ?? `API error: ${response.status}`, response.status);
  }

  return response.json();
}

// BUILD-29: goi qua route noi bo (`app/api/feedback/route.ts`), cung mau
// forward Authorization nguyen ven nhu sendChatMessage o tren - route nay
// khong tu kiem tra role/patient_id, backend that (POST /agent/v2/feedback)
// tu lam dieu do va tra 403 dung thiet ke neu sai.
export async function submitFeedbackReport(
  payload: FeedbackReportRequest,
  accessToken?: string | null,
): Promise<FeedbackReportResponse> {
  const response = await fetch("/api/feedback", {
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
