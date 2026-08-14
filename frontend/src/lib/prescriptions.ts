// Goi POST/GET /api/v1/prescriptions that (qua route noi bo cua chinh FE,
// giu header X-Internal-Secret an toan phia server - cung mau voi lib/api.ts).
//
// Chua co auth-api that, nen "ai dang duyet" phai tam co dinh - cung ly do
// voi DEMO_PATIENT_ID trong lib/api.ts. Gia tri nay KHOP voi doctor_id da gan
// cho 3 benh nhan mau trong scripts/seed_photo_patients.py, de duyet phac do
// tren du lieu that khong bi lech nguoi phu trach.
export const DEMO_DOCTOR_ID = "demo-doctor-01";

export type PrescriptionItemInput = {
  drugId: string | null;
  tenThuoc: string;
  dangThuoc: string | null;
  duongDung: string | null;
  hamLuong: string | null;
  lieuDung: string;
  thoiDiemDung: string | null;
  soVienMoiLan: number | null;
  gioNhac: string[];
  // Khoang ngay RIENG cua thuoc nay - null nghia la dung chung khoang ngay
  // cua ca phac do (Prescription.startDate/durationDays).
  startDate?: string | null;
  durationDays?: number | null;
};

export type PrescriptionRecord = {
  id: string;
  patientId: string;
  doctorId: string;
  status: string; // draft|active|rejected|stopped|completed
  note: string | null;
  startDate: string;
  durationDays: number;
  items: {
    drugId: string;
    tenThuoc: string;
    dangThuoc: string;
    lieuDung: string;
    gioNhac: string[];
    startDate: string | null;
    durationDays: number | null;
  }[];
};

type PrescriptionApiItem = {
  drug_id: string;
  ten_thuoc: string;
  dang_thuoc: string;
  lieu_dung: string;
  gio_nhac: string[];
  start_date: string | null;
  duration_days: number | null;
};

type PrescriptionApiRecord = {
  id: string;
  patient_id: string;
  doctor_id: string;
  status: string;
  note: string | null;
  start_date: string;
  duration_days: number;
  items: PrescriptionApiItem[];
};

function toRecord(p: PrescriptionApiRecord): PrescriptionRecord {
  return {
    id: p.id,
    patientId: p.patient_id,
    doctorId: p.doctor_id,
    status: p.status,
    note: p.note,
    startDate: p.start_date,
    durationDays: p.duration_days,
    items: (p.items ?? []).map((it) => ({
      drugId: it.drug_id,
      tenThuoc: it.ten_thuoc,
      dangThuoc: it.dang_thuoc,
      lieuDung: it.lieu_dung,
      gioNhac: it.gio_nhac ?? [],
      startDate: it.start_date ?? null,
      durationDays: it.duration_days ?? null,
    })),
  };
}

function toApiItem(it: PrescriptionItemInput) {
  return {
    drug_id: it.drugId || undefined,
    ten_thuoc: it.tenThuoc,
    dang_thuoc: it.dangThuoc || undefined,
    duong_dung: it.duongDung || undefined,
    ham_luong: it.hamLuong || undefined,
    lieu_dung: it.lieuDung,
    thoi_diem_dung: it.thoiDiemDung || undefined,
    so_vien_moi_lan: it.soVienMoiLan ?? undefined,
    gio_nhac: it.gioNhac,
    start_date: it.startDate || undefined,
    duration_days: it.durationDays ?? undefined,
  };
}

async function loi(response: Response): Promise<never> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  // Loi nghiep vu tra ve {code,message,details} (backend/services/prescription/
  // errors.py), khac loi HTTP thuong tra chuoi. Bat ca hai hinh dang.
  const message =
    typeof detail === "string"
      ? detail
      : (detail?.message ?? `Yêu cầu thất bại (${response.status})`);
  throw new Error(message);
}

export async function listPrescriptions(params: { patientId?: string; status?: string } = {}) {
  const query = new URLSearchParams();
  if (params.patientId) query.set("patient_id", params.patientId);
  if (params.status) query.set("status", params.status);

  const response = await fetch(`/api/prescriptions?${query.toString()}`);
  if (!response.ok) return loi(response);

  const data: { items: PrescriptionApiRecord[] } = await response.json();
  return data.items.map(toRecord);
}

export async function createPrescription(input: {
  patientId: string;
  doctorId: string;
  note?: string;
  items: PrescriptionItemInput[];
}): Promise<PrescriptionRecord> {
  const response = await fetch("/api/prescriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      patient_id: input.patientId,
      doctor_id: input.doctorId,
      note: input.note || undefined,
      items: input.items.map(toApiItem),
    }),
  });
  if (!response.ok) return loi(response);
  return toRecord(await response.json());
}

export async function updatePrescription(
  prescriptionId: string,
  input: { doctorId?: string; note?: string; items: PrescriptionItemInput[] },
): Promise<PrescriptionRecord> {
  const response = await fetch(`/api/prescriptions/${prescriptionId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doctor_id: input.doctorId ?? DEMO_DOCTOR_ID,
      note: input.note || undefined,
      items: input.items.map(toApiItem),
    }),
  });
  if (!response.ok) return loi(response);
  return toRecord(await response.json());
}

async function quyetDinh(prescriptionId: string, hanhDong: "approve" | "reject", doctorId: string) {
  const response = await fetch(`/api/prescriptions/${prescriptionId}/${hanhDong}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: doctorId }),
  });
  if (!response.ok) return loi(response);
  return response.json();
}

export function approvePrescription(prescriptionId: string, doctorId: string = DEMO_DOCTOR_ID) {
  return quyetDinh(prescriptionId, "approve", doctorId);
}

export function rejectPrescription(prescriptionId: string, doctorId: string = DEMO_DOCTOR_ID) {
  return quyetDinh(prescriptionId, "reject", doctorId);
}
