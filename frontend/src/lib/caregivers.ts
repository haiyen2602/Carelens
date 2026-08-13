// Lien ket nguoi than <-> benh nhan THAT, qua /api/caregiver-links (route noi
// bo cua chinh FE, giu X-Internal-Secret an toan phia server - cung mau voi
// lib/prescriptions.ts). Hai chieu GET khac hinh dang nhau (xem BE contract):
// theo patient_id tra danh sach nguoi than cua 1 benh nhan; theo
// caregiver_account_id tra danh sach benh nhan 1 nguoi than dang theo doi kem
// tom tat tuan thu.

export type CaregiverLink = {
  id: string;
  caregiverAccountId: string;
  caregiverName: string;
  relationship: string;
  createdAt: string;
};

type CaregiverLinkApi = {
  id: string;
  caregiver_account_id: string;
  caregiver_name: string;
  relationship: string;
  created_at: string;
};

export type MonitoredPatient = {
  linkId: string;
  patientId: string;
  fullName: string;
  yearOfBirth: number | null;
  note: string | null;
  relationship: string;
  adherencePct: number | null;
  doseTakenToday: number;
  doseTotalToday: number;
  openEscalations: { id: string; level: string; title: string; createdAt: string }[];
  weekHistory: { date: string; status: "taken" | "late" | "missed" }[];
};

type MonitoredPatientApi = {
  link_id: string;
  patient_id: string;
  full_name: string;
  year_of_birth: number | null;
  note: string | null;
  relationship: string;
  adherence_pct: number | null;
  dose_taken_today: number;
  dose_total_today: number;
  open_escalations: { id: string; level: string; title: string; created_at: string }[];
  week_history: { date: string; status: "taken" | "late" | "missed" }[];
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

function toCaregiverLink(l: CaregiverLinkApi): CaregiverLink {
  return {
    id: l.id,
    caregiverAccountId: l.caregiver_account_id,
    caregiverName: l.caregiver_name,
    relationship: l.relationship,
    createdAt: l.created_at,
  };
}

function toMonitoredPatient(m: MonitoredPatientApi): MonitoredPatient {
  return {
    linkId: m.link_id,
    patientId: m.patient_id,
    fullName: m.full_name,
    yearOfBirth: m.year_of_birth,
    note: m.note,
    relationship: m.relationship,
    adherencePct: m.adherence_pct,
    doseTakenToday: m.dose_taken_today,
    doseTotalToday: m.dose_total_today,
    openEscalations: (m.open_escalations ?? []).map((e) => ({
      id: e.id,
      level: e.level,
      title: e.title,
      createdAt: e.created_at,
    })),
    weekHistory: (m.week_history ?? []).map((h) => ({ date: h.date, status: h.status })),
  };
}

export async function listCaregiverLinksForPatient(patientId: string): Promise<CaregiverLink[]> {
  const response = await fetch(`/api/caregiver-links?patient_id=${encodeURIComponent(patientId)}`);
  if (!response.ok) return loi(response);
  const items: CaregiverLinkApi[] = await response.json();
  return items.map(toCaregiverLink);
}

export async function listMonitoredPatients(caregiverAccountId: string): Promise<MonitoredPatient[]> {
  const response = await fetch(
    `/api/caregiver-links?caregiver_account_id=${encodeURIComponent(caregiverAccountId)}`,
  );
  if (!response.ok) return loi(response);
  const items: MonitoredPatientApi[] = await response.json();
  return items.map(toMonitoredPatient);
}

export async function createCaregiverLink(input: {
  caregiverAccountId: string;
  patientId: string;
  relationship: string;
}): Promise<{ id: string; caregiverAccountId: string; patientId: string; relationship: string; createdAt: string }> {
  const response = await fetch("/api/caregiver-links", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      caregiver_account_id: input.caregiverAccountId,
      patient_id: input.patientId,
      relationship: input.relationship,
    }),
  });
  if (!response.ok) return loi(response);
  const data = await response.json();
  return {
    id: data.id,
    caregiverAccountId: data.caregiver_account_id,
    patientId: data.patient_id,
    relationship: data.relationship,
    createdAt: data.created_at,
  };
}

export async function deleteCaregiverLink(linkId: string): Promise<void> {
  const response = await fetch(`/api/caregiver-links/${encodeURIComponent(linkId)}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 204) return loi(response);
}
