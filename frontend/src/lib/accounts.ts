// Quan ly tai khoan THAT (chi admin), qua /api/accounts (route noi bo cua
// chinh FE, giu X-Internal-Secret an toan phia server - cung mau voi
// lib/prescriptions.ts).

export type AccountRole = "doctor" | "patient" | "caregiver" | "admin";
export type AccountCreationRole = Extract<AccountRole, "doctor" | "admin">;
export type AccountStatus = "active" | "locked" | "pending";

export type AccountRecord = {
  id: string;
  fullName: string;
  email: string;
  role: AccountRole;
  patientId: string | null;
  doctorId: string | null;
  createdAt: string;
  status: AccountStatus;
};

type AccountApi = {
  id: string;
  full_name: string;
  email: string;
  role: AccountRole;
  patient_id: string | null;
  doctor_id: string | null;
  created_at: string;
  status: AccountStatus;
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

function toAccount(a: AccountApi): AccountRecord {
  return {
    id: a.id,
    fullName: a.full_name,
    email: a.email,
    role: a.role,
    patientId: a.patient_id,
    doctorId: a.doctor_id,
    createdAt: a.created_at,
    status: a.status,
  };
}

export async function listAccounts(accessToken?: string | null): Promise<AccountRecord[]> {
  const response = await fetch("/api/accounts", {
    headers: { ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}) },
  });
  if (!response.ok) return loi(response);
  const items: AccountApi[] = await response.json();
  return items.map(toAccount);
}

export async function createAccount(input: {
  fullName: string;
  email: string;
  password: string;
  role: AccountCreationRole;
  accessToken?: string | null;
}): Promise<AccountRecord> {
  const response = await fetch("/api/accounts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(input.accessToken ? { Authorization: `Bearer ${input.accessToken}` } : {}),
    },
    body: JSON.stringify({
      full_name: input.fullName,
      email: input.email,
      password: input.password,
      role: input.role,
    }),
  });
  if (!response.ok) return loi(response);
  return toAccount(await response.json());
}

export async function updateAccountStatus(
  accountId: string,
  status: AccountStatus,
  accessToken?: string | null,
): Promise<AccountRecord> {
  const response = await fetch(`/api/accounts/${encodeURIComponent(accountId)}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) return loi(response);
  return toAccount(await response.json());
}
