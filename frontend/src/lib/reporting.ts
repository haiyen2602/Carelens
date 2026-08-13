// Danh sach benh nhan cho bao cao tuan thu (FEAT-010) + bat/tat theo doi, qua
// /api/reporting/patients (route noi bo cua chinh FE, giu X-Internal-Secret
// an toan phia server - cung mau voi lib/prescriptions.ts).

export type ReportingPatient = {
  id: string;
  fullName: string;
  yearOfBirth: number | null;
  note: string | null;
  gender: string | null;
  heightCm: number | null;
  weightKg: number | null;
  watch: boolean;
  adherencePct: number | null;
};

type ReportingPatientApi = {
  id: string;
  full_name: string;
  year_of_birth: number | null;
  note: string | null;
  gender: string | null;
  height_cm: number | null;
  weight_kg: number | null;
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
    gender: p.gender,
    heightCm: p.height_cm,
    weightKg: p.weight_kg,
    watch: p.watch,
    adherencePct: p.adherence_pct,
  };
}

export async function listReportingPatients(search?: string): Promise<ReportingPatient[]> {
  const qs = search?.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
  const response = await fetch(`/api/reporting/patients${qs}`);
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

export type PatientHealthPatch = {
  note: string | null;
  gender: string | null;
  heightCm: number | null;
  weightKg: number | null;
};

// PATCH /api/v1/patients/{id} tra ve PatientSummary (KHONG co watch/
// adherence_pct - hai truong do thuoc rieng reporting), nen chi tra lai phan
// da doi de goi noi merge vao state hien co, khong dung de thay the ca dong.
export async function updatePatientHealth(
  patientId: string,
  patch: { note?: string; gender?: string; heightCm?: number; weightKg?: number },
): Promise<PatientHealthPatch> {
  const response = await fetch(`/api/patients/${encodeURIComponent(patientId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      note: patch.note,
      gender: patch.gender,
      height_cm: patch.heightCm,
      weight_kg: patch.weightKg,
    }),
  });
  if (!response.ok) return loi(response);
  const p: { note: string | null; gender: string | null; height_cm: number | null; weight_kg: number | null } =
    await response.json();
  return { note: p.note, gender: p.gender, heightCm: p.height_cm, weightKg: p.weight_kg };
}
