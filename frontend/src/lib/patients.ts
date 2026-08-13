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
};

type PatientApiItem = {
  id: string;
  full_name: string;
  year_of_birth: number | null;
  note: string | null;
};

export async function listPatients(search?: string): Promise<PatientRecord[]> {
  const qs = search?.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
  const response = await fetch(`/api/patients${qs}`);
  if (!response.ok) {
    throw new Error(`Không tải được danh sách bệnh nhân (${response.status})`);
  }

  const items: PatientApiItem[] = await response.json();
  return items.map((p) => ({
    id: p.id,
    fullName: p.full_name,
    yearOfBirth: p.year_of_birth,
    note: p.note,
  }));
}
