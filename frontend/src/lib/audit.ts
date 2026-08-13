// Audit log hoi thoai AI THAT (utterance/final_response/trace), qua
// /api/audit-log (route noi bo cua chinh FE, giu X-Internal-Secret an toan
// phia server - cung mau voi lib/prescriptions.ts).

export type AuditLogEntry = {
  id: string;
  patientId: string;
  doseEventId: string | null;
  utterance: string;
  createdAt: string;
  trace: unknown;
  finalResponse: string | null;
  totalDurationMs: number | null;
};

type AuditLogApi = {
  id: string;
  patient_id: string;
  dose_event_id: string | null;
  utterance: string;
  created_at: string;
  trace: unknown;
  final_response: string | null;
  total_duration_ms: number | null;
};

async function loi(response: Response): Promise<never> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  const message =
    typeof detail === "string"
      ? detail
      : (detail?.message ?? `Yêu cầu thất bại (${response.status})`);
  throw new Error(message);
}

function toAuditLogEntry(a: AuditLogApi): AuditLogEntry {
  return {
    id: a.id,
    patientId: a.patient_id,
    doseEventId: a.dose_event_id,
    utterance: a.utterance,
    createdAt: a.created_at,
    trace: a.trace,
    finalResponse: a.final_response,
    totalDurationMs: a.total_duration_ms,
  };
}

export async function listAuditLog(patientId?: string): Promise<AuditLogEntry[]> {
  const query = new URLSearchParams();
  if (patientId) query.set("patient_id", patientId);

  const response = await fetch(`/api/audit-log?${query.toString()}`);
  if (!response.ok) return loi(response);
  const items: AuditLogApi[] = await response.json();
  return items.map(toAuditLogEntry);
}
