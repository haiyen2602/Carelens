export type AccountRole = "doctor" | "patient" | "caregiver" | "admin";
export type AccountStatus = "active" | "locked" | "pending";

export type Account = {
  id: string;
  name: string;
  phone: string;
  email: string;
  role: AccountRole;
  status: AccountStatus;
  createdAt: string;
  lastLogin: string;
};

export const ACCOUNTS: Account[] = [
  {
    id: "ADM-001",
    name: "Nguyễn Hải Yến",
    phone: "0912 345 678",
    email: "yen.nguyen@capymedi.dev",
    role: "admin",
    status: "active",
    createdAt: "12/01/2026",
    lastLogin: "Hôm nay, 08:10",
  },
  {
    id: "BS-0114",
    name: "BS. Phạm Quốc Huy",
    phone: "0908 221 456",
    email: "huy.pham@capymedi.dev",
    role: "doctor",
    status: "active",
    createdAt: "03/02/2026",
    lastLogin: "Hôm nay, 07:52",
  },
  {
    id: "BS-0128",
    name: "BS. Đặng Minh Tâm",
    phone: "0977 664 231",
    email: "tam.dang@capymedi.dev",
    role: "doctor",
    status: "active",
    createdAt: "18/02/2026",
    lastLogin: "Hôm qua, 18:44",
  },
  {
    id: "BN-2049",
    name: "Nguyễn Thị Lan",
    phone: "0987 654 321",
    email: "-",
    role: "patient",
    status: "active",
    createdAt: "05/03/2026",
    lastLogin: "Hôm nay, 09:47",
  },
  {
    id: "BN-2050",
    name: "Trần Văn Minh",
    phone: "0913 552 908",
    email: "-",
    role: "patient",
    status: "active",
    createdAt: "05/03/2026",
    lastLogin: "Hôm nay, 07:05",
  },
  {
    id: "BN-2051",
    name: "Lê Thị Hoa",
    phone: "0934 771 220",
    email: "-",
    role: "patient",
    status: "locked",
    createdAt: "11/03/2026",
    lastLogin: "3 ngày trước",
  },
  {
    id: "CG-3011",
    name: "Trần Bích Ngọc",
    phone: "0965 118 402",
    email: "ngoc.tran@gmail.com",
    role: "caregiver",
    status: "active",
    createdAt: "06/03/2026",
    lastLogin: "Hôm nay, 21:16",
  },
  {
    id: "CG-3012",
    name: "Lê Hoàng Nam",
    phone: "0901 226 774",
    email: "nam.le@gmail.com",
    role: "caregiver",
    status: "pending",
    createdAt: "20/07/2026",
    lastLogin: "Chưa đăng nhập",
  },
];

export type PatientLink = {
  id: string;
  patient: string;
  patientId: string;
  doctor: string;
  doctorId: string;
  caregivers: { id: string; name: string; relationship: string }[];
};

export const LINKS: PatientLink[] = [
  {
    id: "LNK-01",
    patient: "Nguyễn Thị Lan",
    patientId: "BN-2049",
    doctor: "BS. Phạm Quốc Huy",
    doctorId: "BS-0114",
    caregivers: [{ id: "CG-3011", name: "Trần Bích Ngọc", relationship: "Con gái" }],
  },
  {
    id: "LNK-02",
    patient: "Trần Văn Minh",
    patientId: "BN-2050",
    doctor: "BS. Phạm Quốc Huy",
    doctorId: "BS-0114",
    caregivers: [
      { id: "CG-3012", name: "Lê Hoàng Nam", relationship: "Con rể" },
      { id: "CG-3013", name: "Trần Thị Hạnh", relationship: "Vợ" },
    ],
  },
  {
    id: "LNK-03",
    patient: "Lê Thị Hoa",
    patientId: "BN-2051",
    doctor: "BS. Đặng Minh Tâm",
    doctorId: "BS-0128",
    caregivers: [],
  },
];

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
