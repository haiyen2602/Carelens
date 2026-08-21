// Canh bao/escalation THAT (bo lieu, trieu chung nghiem trong...), qua
// /api/escalations (route noi bo cua chinh FE, giu X-Internal-Secret an toan
// phia server - cung mau voi lib/prescriptions.ts). Chua co endpoint sua
// trang thai escalation ben backend (chi co GET) - xem proto-store.tsx.

export type Severity = "LOW" | "MEDIUM" | "HIGH";
export type EscalationStatus = "OPEN" | "ACKED" | "RESOLVED";

export type Escalation = {
  id: string;
  patientId: string;
  doseEventId: string | null;
  severity: Severity;
  trigger: string;
  rawUtterance: string | null;
  reason: string | null;
  createdAt: string;
  status: EscalationStatus;
  notified: boolean;
  reminderCount: number;
  lastReminderAt: string | null;
  resolvedAt: string | null;
  resolvedBy: string | null;
};

type EscalationApi = {
  id: string;
  patient_id: string;
  dose_event_id: string | null;
  severity: Severity;
  trigger: string;
  raw_utterance: string | null;
  reason: string | null;
  created_at: string;
  status: EscalationStatus;
  notified: boolean;
  reminder_count: number;
  last_reminder_at: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
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

function toEscalation(e: EscalationApi): Escalation {
  return {
    id: e.id,
    patientId: e.patient_id,
    doseEventId: e.dose_event_id,
    severity: e.severity,
    trigger: e.trigger,
    rawUtterance: e.raw_utterance,
    reason: e.reason,
    createdAt: e.created_at,
    status: e.status,
    notified: e.notified,
    reminderCount: e.reminder_count,
    lastReminderAt: e.last_reminder_at,
    resolvedAt: e.resolved_at,
    resolvedBy: e.resolved_by,
  };
}

export async function listEscalations(
  params: { patientId?: string; status?: string } = {},
  accessToken?: string | null,
): Promise<Escalation[]> {
  const query = new URLSearchParams();
  if (params.patientId) query.set("patient_id", params.patientId);
  if (params.status) query.set("status", params.status);

  const response = await fetch(`/api/escalations?${query.toString()}`, {
    headers: { ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
  });
  if (!response.ok) return loi(response);
  const items: EscalationApi[] = await response.json();
  return items.map(toEscalation);
}

// API_BASE trung voi lib/nudges.ts/lib/caregivers.ts - 2 ham duoi day goi
// THANG backend kem Bearer (khong qua route noi bo /api/escalations o tren,
// vi can biet DUNG ai dang goi de kiem tra quyen, cung ly do voi cac ham
// invite/accept trong lib/caregivers.ts).
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Danh dau 1 escalation da duoc nguoi than/bac si xu ly xong -
 * backend/api/escalation_routes.py::ack_escalation tu kiem tra quyen theo
 * JWT (doctor/caregiver/admin, hoac patient dang theo doi nhu nguoi than). */
export async function ackEscalation(accessToken: string, escalationId: string): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/v1/escalations/${encodeURIComponent(escalationId)}/ack`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
    },
  );
  if (!response.ok) return loi(response);
}

/** Benh nhan tu ghi nhat ky suc khoe (health/page.tsx) - "mid"/"high" tao
 * Escalation that de nguoi than thay (backend/api/health_log_routes.py),
 * "low" chi luu nhat ky rieng, khong tao gi ca. */
export async function reportHealthIssue(
  accessToken: string,
  input: { text: string; level: "low" | "mid" | "high" },
): Promise<{ escalationId: string | null }> {
  const response = await fetch(`${API_BASE}/api/v1/health-log`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ text: input.text, level: input.level }),
  });
  if (!response.ok) return loi(response);
  const data = await response.json();
  return { escalationId: data.escalation_id ?? null };
}
