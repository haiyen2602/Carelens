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
  phone: string | null;
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
  phone?: string | null;
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
    phone: p.phone ?? null,
    watch: p.watch,
    adherencePct: p.adherence_pct,
  };
}

export async function listReportingPatients(
  search?: string,
  accessToken?: string | null,
): Promise<ReportingPatient[]> {
  const qs = search?.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
  const response = await fetch(`/api/reporting/patients${qs}`, {
    headers: { ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
  });
  if (!response.ok) return loi(response);
  const items: ReportingPatientApi[] = await response.json();
  return items.map(toReportingPatient);
}

export async function setPatientWatch(
  patientId: string,
  watch: boolean,
  accessToken?: string | null,
): Promise<{ id: string; watch: boolean }> {
  const response = await fetch(`/api/reporting/patients/${encodeURIComponent(patientId)}/watch`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
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
  accessToken?: string | null,
): Promise<PatientHealthPatch> {
  const response = await fetch(`/api/patients/${encodeURIComponent(patientId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({
      note: patch.note,
      gender: patch.gender,
      height_cm: patch.heightCm,
      weight_kg: patch.weightKg,
    }),
  });
  if (!response.ok) return loi(response);
  const p: {
    note: string | null;
    gender: string | null;
    height_cm: number | null;
    weight_kg: number | null;
  } = await response.json();
  return { note: p.note, gender: p.gender, heightCm: p.height_cm, weightKg: p.weight_kg };
}

// --- Tong hop lieu cho trang "Tổng quan thông tin" -----------------------
//
// Goi THANG backend kem Bearer: backend gioi han pham vi theo DoctorWatch cua
// chinh nguoi dang dang nhap (doc tu JWT), nen phai biet dung ai dang goi -
// khong di qua route noi bo /api/reporting/* nhu listReportingPatients().
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type DoseDay = {
  date: string;
  taken: number;
  delayed: number;
  missed: number;
  total: number;
};

export type MissedWindow = {
  key: string;
  label: string;
  missed: number;
};

export type AdherenceBucket = {
  key: string;
  label: string;
  count: number;
};

export type PatientAdherence = {
  patientId: string;
  fullName: string;
  note: string | null;
  adherencePct: number | null;
  due: number;
  taken: number;
};

export type PeriodTotals = {
  averageAdherencePct: number | null;
  due: number;
  taken: number;
  delayed: number;
  missed: number;
};

export type DoseSummary = {
  days: number;
  fromDate: string;
  toDate: string;
  patientCount: number;
  withDataCount: number;
  withoutDataCount: number;
  highRiskCount: number;
  current: PeriodTotals;
  previous: PeriodTotals;
  buckets: AdherenceBucket[];
  patients: PatientAdherence[];
  daily: DoseDay[];
  missedByWindow: MissedWindow[];
};

type PeriodTotalsApi = {
  average_adherence_pct: number | null;
  due: number;
  taken: number;
  delayed: number;
  missed: number;
};

function toPeriodTotals(p: PeriodTotalsApi): PeriodTotals {
  return {
    averageAdherencePct: p.average_adherence_pct,
    due: p.due,
    taken: p.taken,
    delayed: p.delayed,
    missed: p.missed,
  };
}

export async function getDoseSummary(accessToken: string, days = 7): Promise<DoseSummary> {
  const response = await fetch(`${API_BASE}/api/v1/reporting/dose-summary?days=${days}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) return loi(response);
  const data: {
    days: number;
    from_date: string;
    to_date: string;
    patient_count: number;
    with_data_count: number;
    without_data_count: number;
    high_risk_count: number;
    current: PeriodTotalsApi;
    previous: PeriodTotalsApi;
    buckets: AdherenceBucket[];
    patients: {
      patient_id: string;
      full_name: string;
      note: string | null;
      adherence_pct: number | null;
      due: number;
      taken: number;
    }[];
    daily: DoseDay[];
    missed_by_window: MissedWindow[];
  } = await response.json();

  return {
    days: data.days,
    fromDate: data.from_date,
    toDate: data.to_date,
    patientCount: data.patient_count,
    withDataCount: data.with_data_count,
    withoutDataCount: data.without_data_count,
    highRiskCount: data.high_risk_count,
    current: toPeriodTotals(data.current),
    previous: toPeriodTotals(data.previous),
    buckets: data.buckets,
    patients: data.patients.map((p) => ({
      patientId: p.patient_id,
      fullName: p.full_name,
      note: p.note,
      adherencePct: p.adherence_pct,
      due: p.due,
      taken: p.taken,
    })),
    daily: data.daily,
    missedByWindow: data.missed_by_window,
  };
}
