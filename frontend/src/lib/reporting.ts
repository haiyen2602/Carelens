// Danh sach benh nhan cho bao cao tuan thu (FEAT-010) + bat/tat theo doi, qua
// /api/reporting/patients (route noi bo cua chinh FE, giu X-Internal-Secret
// an toan phia server - cung mau voi lib/prescriptions.ts).

export type ReportingPatient = {
  id: string;
  fullName: string;
  yearOfBirth: number | null;
  note: string | null;
  watch: boolean;
  adherencePct: number | null;
};

type ReportingPatientApi = {
  id: string;
  full_name: string;
  year_of_birth: number | null;
  note: string | null;
  watch: boolean;
  adherence_pct: number | null;
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

function toReportingPatient(p: ReportingPatientApi): ReportingPatient {
  return {
    id: p.id,
    fullName: p.full_name,
    yearOfBirth: p.year_of_birth,
    note: p.note,
    watch: p.watch,
    adherencePct: p.adherence_pct,
  };
}

export async function listReportingPatients(): Promise<ReportingPatient[]> {
  const response = await fetch("/api/reporting/patients");
  if (!response.ok) return loi(response);
  const items: ReportingPatientApi[] = await response.json();
  return items.map(toReportingPatient);
}

export async function setPatientWatch(patientId: string, watch: boolean): Promise<{ id: string; watch: boolean }> {
  const response = await fetch(`/api/reporting/patients/${encodeURIComponent(patientId)}/watch`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ watch }),
  });
  if (!response.ok) return loi(response);
  return response.json();
}
