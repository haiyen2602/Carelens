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
