import { request } from "@/lib/api";

// account-api (follow-up TASK-010, specs/api-contracts.md muc 1b) - chi
// role=admin duoc goi. Goi truc tiep backend kem Authorization: Bearer
// (access_token tu useAuth()) - khac /api/auth/* (khong can Route Handler
// proxy o day vi khong lien quan httpOnly cookie).
export type AccountRole = "doctor" | "patient" | "caregiver" | "admin";
export type AccountStatus = "active" | "locked";

export type Account = {
  id: string;
  full_name: string;
  email: string;
  role: AccountRole;
  status: AccountStatus;
  patient_id: string | null;
  doctor_id: string | null;
  created_at: string;
};

export type CreateAccountPayload = {
  email: string;
  password: string;
  full_name: string;
  role: AccountRole;
  patient_id?: string | null;
  doctor_id?: string | null;
};

export const roleLabel: Record<AccountRole, string> = {
  doctor: "Bác sĩ",
  patient: "Bệnh nhân",
  caregiver: "Người thân",
  admin: "Quản trị",
};

export const statusLabel: Record<AccountStatus, string> = {
  active: "Hoạt động",
  locked: "Đã khoá",
};

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export function listAccounts(token: string): Promise<Account[]> {
  return request<Account[]>("/api/v1/accounts", { headers: authHeaders(token) });
}

export function createAccount(token: string, payload: CreateAccountPayload): Promise<Account> {
  return request<Account>("/api/v1/accounts", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export function updateAccountStatus(
  token: string,
  id: string,
  status: AccountStatus,
): Promise<Account> {
  return request<Account>(`/api/v1/accounts/${id}/status`, {
    method: "PATCH",
    headers: authHeaders(token),
    body: JSON.stringify({ status }),
  });
}
