// System Audit Logs (Bảng system_audit_logs - Quản trị hệ thống)
export type SystemAuditLogEntry = {
  id: string;
  actor_id: string | null;
  actor_name: string;
  actor_role: string;
  action: string;
  target: string | null;
  created_at: string;
};

export type SystemAuditLogResponse = {
  items: SystemAuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

// Chatbot RAG Audit Logs (Bảng audit_log - Luồng hội thoại bệnh nhân)
export type AuditLogEntry = {
  id: string;
  patientId: string;
  doseEventId: string | null;
  utterance: string;
  createdAt: string;
  trace: unknown[];
  finalResponse: string;
  totalDurationMs: number;
};

type AuditLogApi = {
  id: string;
  patient_id: string;
  dose_event_id: string | null;
  utterance: string;
  created_at: string;
  trace: unknown[];
  final_response: string;
  total_duration_ms: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listSystemAuditLogs(
  options: {
    q?: string;
    role?: string;
    page?: number;
    pageSize?: number;
    accessToken?: string | null;
    signal?: AbortSignal;
  } = {},
): Promise<SystemAuditLogResponse> {
  const params = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 20),
  });
  if (options.q?.trim()) params.set("q", options.q.trim());
  if (options.role && options.role !== "all") params.set("role", options.role);

  const response = await fetch(`${API_BASE}/api/v1/admin/audit-logs?${params}`, {
    signal: options.signal,
    headers: options.accessToken ? { Authorization: `Bearer ${options.accessToken}` } : undefined,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Không thể tải log hệ thống (${response.status})`,
    );
  }

  return response.json() as Promise<SystemAuditLogResponse>;
}

function toAuditLogEntry(a: AuditLogApi): AuditLogEntry {
  return {
    id: a.id,
    patientId: a.patient_id,
    doseEventId: a.dose_event_id,
    utterance: a.utterance,
    createdAt: a.created_at,
    trace: a.trace ?? [],
    finalResponse: a.final_response,
    totalDurationMs: a.total_duration_ms,
  };
}

export async function listAuditLog(
  patientId?: string,
  accessToken?: string | null,
): Promise<AuditLogEntry[]> {
  const url = patientId
    ? `/api/audit-log?patient_id=${encodeURIComponent(patientId)}`
    : "/api/audit-log";
  const response = await fetch(url, {
    headers: { ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Tải audit log thất bại (${response.status})`);
  }
  const items: AuditLogApi[] = await response.json();
  return items.map(toAuditLogEntry);
}

// --- Nhat ky THAO TAC cua chinh nguoi dang dang nhap ---------------------
//
// KHAC listAuditLog() o tren: ham do tra ve hoi thoai AI cua BENH NHAN (cau
// hoi + cau tra loi cua tro ly). Duoi day la viec BAC SI da lam (duyet phac
// do, xu ly canh bao, sua ho so...) - doc tu bang system_audit_logs.
//
// Goi THANG backend kem Bearer (dung lai API_BASE khai bao o tren file nay),
// khong qua route noi bo /api/*: backend lay actor_id tu chinh JWT (khong
// nhan tu query param) nen phai biet dung ai dang goi - cung ly do voi
// ackEscalation() trong lib/escalations.ts.

export type MyAction = {
  id: string;
  action: string;
  target: string | null;
  actorName: string;
  actorRole: string;
  createdAt: string;
};

export type MyActionsPage = {
  items: MyAction[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

type MyActionApi = {
  id: string;
  actor_id: string | null;
  actor_name: string;
  actor_role: string;
  action: string;
  target: string | null;
  created_at: string;
};

export async function listMyActions(
  accessToken: string,
  params: { q?: string; page?: number; pageSize?: number } = {},
): Promise<MyActionsPage> {
  const query = new URLSearchParams();
  if (params.q?.trim()) query.set("q", params.q.trim());
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 20));

  const response = await fetch(`${API_BASE}/api/v1/audit-logs/me?${query.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Tải nhật ký thao tác thất bại (${response.status})`);
  }
  const data: {
    items: MyActionApi[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  } = await response.json();

  return {
    items: data.items.map((a) => ({
      id: a.id,
      action: a.action,
      target: a.target,
      actorName: a.actor_name,
      actorRole: a.actor_role,
      createdAt: a.created_at,
    })),
    total: data.total,
    page: data.page,
    pageSize: data.page_size,
    totalPages: data.total_pages,
  };
}
