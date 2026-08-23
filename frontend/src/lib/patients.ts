// Danh sach benh nhan THAT tu backend (bang `patient`), dung cho form ke don.
//
// KHONG dung chung voi mang `patients` mock trong proto-store.tsx: mock do
// mang theo age/condition/adherence/watch - du lieu cho dashboard tuan thu
// (FEAT-010), CHUA co ben backend (chua xay bao cao tuan thu). Tron hai nguon
// vao mot se lam 8 trang dang doc mock hong vi thieu nhung truong do. Danh
// sach o day CHI phuc vu dung 1 viec: chon dung `patient_id` that khi tao don.

export type PatientRecord = {
  id: string;
  fullName: string;
  yearOfBirth: number | null;
  note: string | null;
  gender: string | null;
  heightCm: number | null;
  weightKg: number | null;
};

type PatientApiItem = {
  id: string;
  full_name: string;
  year_of_birth: number | null;
  note: string | null;
  gender?: string | null;
  height_cm?: number | null;
  weight_kg?: number | null;
};

function toRecord(p: PatientApiItem): PatientRecord {
  return {
    id: p.id,
    fullName: p.full_name,
    yearOfBirth: p.year_of_birth,
    note: p.note,
    gender: p.gender ?? null,
    heightCm: p.height_cm ?? null,
    weightKg: p.weight_kg ?? null,
  };
}

// Ho so CA NHAN day du cua CHINH benh nhan dang dang nhap - khac PatientRecord
// (dung cho danh sach/tim kiem, khong co phone/address/date_of_birth vi la
// thong tin rieng tu, xem _to_summary(full=False) o backend). Khop voi
// backend/models/schemas.py::PatientProfileOut, tra ve tu ca GET lan PATCH
// /api/patients/me (backend/api/patient_routes.py).
export type PatientProfile = {
  id: string;
  fullName: string;
  dateOfBirth: string | null;
  yearOfBirth: number | null;
  phone: string | null;
  address: string | null;
  gender: string | null;
  heightCm: number | null;
  weightKg: number | null;
  profileCompleted: boolean;
};

type PatientProfileApiItem = {
  id: string;
  full_name: string;
  date_of_birth: string | null;
  year_of_birth: number | null;
  phone: string | null;
  address: string | null;
  gender: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  profile_completed: boolean;
};

function toProfile(p: PatientProfileApiItem): PatientProfile {
  return {
    id: p.id,
    fullName: p.full_name,
    dateOfBirth: p.date_of_birth,
    yearOfBirth: p.year_of_birth,
    phone: p.phone,
    address: p.address,
    gender: p.gender,
    heightCm: p.height_cm,
    weightKg: p.weight_kg,
    profileCompleted: p.profile_completed,
  };
}

export async function listPatients(
  search?: string,
  accessToken?: string | null,
): Promise<PatientRecord[]> {
  const qs = search?.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
  const response = await fetch(`/api/patients${qs}`, {
    headers: { ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
  });
  if (!response.ok) {
    throw new Error(`Không tải được danh sách bệnh nhân (${response.status})`);
  }

  const items: PatientApiItem[] = await response.json();
  return items.map(toRecord);
}

// Sua tinh trang suc khoe: dung updatePatientHealth() trong lib/reporting.ts
// (cung endpoint PATCH /api/patients/{id}) - khong nhan ban o day.

// Phan hoi review 2026-08-14: listPatients() chi doctor/admin (backend
// require_role) - benh nhan tu goi se 403. Ham rieng nay goi
// GET /api/patients/me (backend/api/patient_routes.py::get_my_patient_profile),
// tu doc patient_id qua JWT, khong nhan id tu client - dung cho trang benh
// nhan tu xem ho so CHINH minh (vd patient/health/page.tsx).
export async function getMyPatientProfile(
  accessToken?: string | null,
): Promise<PatientProfile | null> {
  const response = await fetch("/api/patients/me", {
    headers: { ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
  });
  if (response.status === 403 || response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Không tải được hồ sơ bệnh nhân (${response.status})`);
  }

  return toProfile(await response.json());
}

// Man hinh "Doi thong tin ca nhan" (components/edit-personal-info-dialog.tsx)
// - cung endpoint PATCH /api/patients/me ma onboarding/profile/page.tsx dang
// goi thang qua fetch(), gop lai 1 cho de dung chung thay vi nhan ban logic
// header/loi. KHONG doi onboarding sang dung ham nay trong lan sua nay (giu
// nguyen, tranh dong cham code khong lien quan).
export async function updateMyPatientProfile(
  accessToken: string | null | undefined,
  body: {
    date_of_birth?: string;
    phone?: string;
    address?: string;
    gender?: string;
    height_cm?: number;
    weight_kg?: number;
  },
): Promise<PatientProfile> {
  const response = await fetch("/api/patients/me", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail ?? "Lưu thông tin thất bại.");
  }
  return toProfile(data);
}
