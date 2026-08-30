// BUILD-44: Doctor Chat Queue & Takeover - typed client for
// /api/doctor/reviews/* (proxied to backend /api/v1/doctor/reviews/*, see
// app/api/doctor/reviews/*/route.ts). Cung quy uoc voi lib/patients.ts:
// fetch tuong doi + Authorization: Bearer <accessToken>, nem Error() khi
// khong ok de trang goi tu quyet dinh hien thi loi the nao.

export type DoctorReviewQueueItem = {
  handoffId: string;
  patientId: string;
  patientName: string;
  conversationId: string | null;
  handoffType: "SAFETY" | "UNCERTAINTY" | "USER_REQUEST";
  reasonCode: string;
  riskDisposition: string;
  status: "PENDING" | "ASSIGNED" | "ACTIVE" | "RESOLVED" | "ANSWERED" | "CANCELLED";
  patientQuestion: string;
  createdAt: string;
  assignedDoctorId: string | null;
  assignedAt: string | null;
  activatedAt: string | null;
  resolvedAt: string | null;
};

export type DoctorReviewMessage = {
  id: string;
  senderRole: "PATIENT" | "DOCTOR" | "SYSTEM";
  actorId: string | null;
  content: string;
  createdAt: string;
  imageAttachmentId: string | null;
};

export type DoctorReviewDetail = DoctorReviewQueueItem & {
  resolvedByDoctorId: string | null;
  messages: DoctorReviewMessage[];
  chatHistory: Array<{ id: string; role: string; content: string; createdAt: string }>;
};

type QueueItemApi = {
  handoff_id: string;
  patient_id: string;
  patient_name: string;
  conversation_id: string | null;
  handoff_type: string;
  reason_code: string;
  risk_disposition: string;
  status: string;
  patient_question: string;
  created_at: string;
  assigned_doctor_id: string | null;
  assigned_at: string | null;
  activated_at: string | null;
  resolved_at: string | null;
};

type MessageApi = {
  id: string;
  sender_role: string;
  actor_id: string | null;
  content: string;
  created_at: string;
  image_attachment_id: string | null;
};

type DetailApi = QueueItemApi & {
  resolved_by_doctor_id: string | null;
  messages: MessageApi[];
  chat_history: Array<{ id: string; role: string; content: string; created_at: string }>;
};

function toQueueItem(item: QueueItemApi): DoctorReviewQueueItem {
  return {
    handoffId: item.handoff_id,
    patientId: item.patient_id,
    patientName: item.patient_name,
    conversationId: item.conversation_id,
    handoffType: item.handoff_type as DoctorReviewQueueItem["handoffType"],
    reasonCode: item.reason_code,
    riskDisposition: item.risk_disposition,
    status: item.status as DoctorReviewQueueItem["status"],
    patientQuestion: item.patient_question,
    createdAt: item.created_at,
    assignedDoctorId: item.assigned_doctor_id,
    assignedAt: item.assigned_at,
    activatedAt: item.activated_at,
    resolvedAt: item.resolved_at,
  };
}

function toMessage(m: MessageApi): DoctorReviewMessage {
  return {
    id: m.id,
    senderRole: m.sender_role as DoctorReviewMessage["senderRole"],
    actorId: m.actor_id,
    content: m.content,
    createdAt: m.created_at,
    imageAttachmentId: m.image_attachment_id,
  };
}

function toDetail(d: DetailApi): DoctorReviewDetail {
  return {
    ...toQueueItem(d),
    resolvedByDoctorId: d.resolved_by_doctor_id,
    messages: d.messages.map(toMessage),
    chatHistory: d.chat_history.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      createdAt: message.created_at,
    })),
  };
}

function authHeaders(accessToken?: string | null): Record<string, string> {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

async function parseErrorDetail(response: Response): Promise<string | null> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

export type QueueFilters = {
  status?: string;
  handoffType?: string;
  assignedToMe?: boolean;
};

export async function listDoctorReviewQueue(
  filters: QueueFilters,
  accessToken?: string | null,
): Promise<{ items: DoctorReviewQueueItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (filters.status) qs.set("status", filters.status);
  if (filters.handoffType) qs.set("handoff_type", filters.handoffType);
  if (filters.assignedToMe) qs.set("assigned_to_me", "true");
  const suffix = qs.toString() ? `?${qs.toString()}` : "";

  const response = await fetch(`/api/doctor/reviews${suffix}`, {
    headers: authHeaders(accessToken),
  });
  if (!response.ok) {
    throw new Error(
      (await parseErrorDetail(response)) ?? `Không tải được hàng đợi (${response.status})`,
    );
  }
  const body: { items: QueueItemApi[]; total: number } = await response.json();
  return { items: body.items.map(toQueueItem), total: body.total };
}

export async function getDoctorReviewDetail(
  handoffId: string,
  accessToken?: string | null,
): Promise<DoctorReviewDetail> {
  const response = await fetch(`/api/doctor/reviews/${encodeURIComponent(handoffId)}`, {
    headers: authHeaders(accessToken),
  });
  if (!response.ok) {
    throw new Error(
      (await parseErrorDetail(response)) ?? `Không tải được yêu cầu (${response.status})`,
    );
  }
  return toDetail(await response.json());
}

export async function getDoctorReviewImageAttachment(
  handoffId: string,
  attachmentId: string,
  accessToken?: string | null,
): Promise<Blob> {
  const response = await fetch(
    `/api/doctor/reviews/${encodeURIComponent(handoffId)}/image-attachments/${encodeURIComponent(attachmentId)}`,
    { headers: authHeaders(accessToken) },
  );
  if (!response.ok) {
    throw new Error(
      (await parseErrorDetail(response)) ?? `Không tải được ảnh bệnh nhân (${response.status})`,
    );
  }
  return response.blob();
}

async function postAction(path: string, accessToken?: string | null): Promise<DoctorReviewDetail> {
  const response = await fetch(path, { method: "POST", headers: authHeaders(accessToken) });
  if (!response.ok) {
    throw new Error((await parseErrorDetail(response)) ?? `Thao tác thất bại (${response.status})`);
  }
  return toDetail(await response.json());
}

export function claimDoctorReview(
  handoffId: string,
  accessToken?: string | null,
): Promise<DoctorReviewDetail> {
  return postAction(`/api/doctor/reviews/${encodeURIComponent(handoffId)}/claim`, accessToken);
}

export function activateDoctorReview(
  handoffId: string,
  accessToken?: string | null,
): Promise<DoctorReviewDetail> {
  return postAction(`/api/doctor/reviews/${encodeURIComponent(handoffId)}/activate`, accessToken);
}

export function resolveDoctorReview(
  handoffId: string,
  accessToken?: string | null,
): Promise<DoctorReviewDetail> {
  return postAction(`/api/doctor/reviews/${encodeURIComponent(handoffId)}/resolve`, accessToken);
}

export function cancelDoctorReview(
  handoffId: string,
  accessToken?: string | null,
): Promise<DoctorReviewDetail> {
  return postAction(`/api/doctor/reviews/${encodeURIComponent(handoffId)}/cancel`, accessToken);
}

export async function sendDoctorReviewMessage(
  handoffId: string,
  content: string,
  accessToken?: string | null,
): Promise<DoctorReviewDetail> {
  const response = await fetch(`/api/doctor/reviews/${encodeURIComponent(handoffId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(accessToken) },
    body: JSON.stringify({ content }),
  });
  if (!response.ok) {
    throw new Error(
      (await parseErrorDetail(response)) ?? `Gửi tin nhắn thất bại (${response.status})`,
    );
  }
  return toDetail(await response.json());
}
