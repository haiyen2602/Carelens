export type AccountRole = "doctor" | "patient" | "caregiver" | "admin";
export type AccountStatus = "active" | "locked" | "pending";

export type MedicineStatus = "indexed" | "processing" | "error";

export type MedicineEntry = {
  id: string;
  name: string;
  activeIngredient: string;
  category: string;
  source: string;
  version: string;
  updatedAt: string;
  status: MedicineStatus;
};

export const MEDICINES: MedicineEntry[] = [
  {
    id: "MED-001",
    name: "Paracetamol 500mg",
    activeIngredient: "Paracetamol",
    category: "Giảm đau, hạ sốt",
    source: "Dược thư Quốc gia VN 2022",
    version: "v3",
    updatedAt: "Hôm nay, 10:02",
    status: "indexed",
  },
  {
    id: "MED-002",
    name: "Amlodipine 5mg",
    activeIngredient: "Amlodipine besylate",
    category: "Tim mạch — hạ huyết áp",
    source: "MIMS Vietnam",
    version: "v2",
    updatedAt: "Hôm qua, 16:20",
    status: "indexed",
  },
  {
    id: "MED-003",
    name: "Metformin 850mg",
    activeIngredient: "Metformin HCl",
    category: "Đái tháo đường",
    source: "Dược thư Quốc gia VN 2022",
    version: "v4",
    updatedAt: "Hôm qua, 16:20",
    status: "indexed",
  },
  {
    id: "MED-004",
    name: "Atorvastatin 20mg",
    activeIngredient: "Atorvastatin calcium",
    category: "Rối loạn lipid máu",
    source: "MIMS Vietnam",
    version: "v1",
    updatedAt: "2 ngày trước",
    status: "processing",
  },
  {
    id: "MED-005",
    name: "Losartan 50mg",
    activeIngredient: "Losartan potassium",
    category: "Tim mạch — hạ huyết áp",
    source: "Tự nhập (CSV nội bộ)",
    version: "v1",
    updatedAt: "5 ngày trước",
    status: "error",
  },
];

export type SystemAuditEntry = {
  id: string;
  at: string;
  date: string;
  actor: string;
  role: AccountRole | "Hệ thống";
  action: string;
  target?: string;
};

export const SYSTEM_AUDIT: SystemAuditEntry[] = [
  {
    id: "SA-01",
    date: "10/08/2026",
    at: "10:02",
    actor: "Nguyễn Hải Yến",
    role: "admin",
    action: "Cập nhật dữ liệu thuốc Paracetamol 500mg (v3) cho RAG",
    target: "MED-001",
  },
  {
    id: "SA-02",
    date: "10/08/2026",
    at: "08:10",
    actor: "Nguyễn Hải Yến",
    role: "admin",
    action: "Đăng nhập vào bảng quản trị hệ thống",
  },
  {
    id: "SA-03",
    date: "09/08/2026",
    at: "18:44",
    actor: "BS. Đặng Minh Tâm",
    role: "doctor",
    action: "Duyệt phác đồ Atorvastatin 20mg cho Lê Thị Hoa",
    target: "BN-2051",
  },
  {
    id: "SA-04",
    date: "09/08/2026",
    at: "14:12",
    actor: "Nguyễn Hải Yến",
    role: "admin",
    action: "Khoá tài khoản BN-2051 (Lê Thị Hoa) — nghi ngờ đăng nhập bất thường",
    target: "BN-2051",
  },
  {
    id: "SA-05",
    date: "08/08/2026",
    at: "09:30",
    actor: "Hệ thống",
    role: "Hệ thống",
    action: "Đồng bộ liên kết bệnh nhân ↔ bác sĩ ↔ người thân (3 bản ghi)",
  },
  {
    id: "SA-06",
    date: "07/08/2026",
    at: "16:20",
    actor: "Nguyễn Hải Yến",
    role: "admin",
    action: "Nạp mới dữ liệu thuốc Metformin 850mg (v4) cho RAG",
    target: "MED-003",
  },
];

export const roleLabel: Record<AccountRole, string> = {
  doctor: "Bác sĩ",
  patient: "Bệnh nhân",
  caregiver: "Người thân",
  admin: "Quản trị",
};

export const statusLabel: Record<AccountStatus, string> = {
  active: "Hoạt động",
  locked: "Đã khoá",
  pending: "Chờ kích hoạt",
};
