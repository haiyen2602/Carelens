// Yeu cau bo sung thuoc ngoai danh muc (FB-14).
//
// Tu 2026-08-20 danh muc thuoc la allowlist dong: bac si khong ke duoc thuoc
// khong chon tu goi y. Day la duong thoat - bac si gui yeu cau, admin duyet,
// duyet xong moi ke duoc.
//
// Goi THANG backend kem Bearer token (khong qua route handler /api/* nhu
// lib/drugs.ts): cac endpoint nay dung require_role() doc JWT that, khong
// dung X-Internal-Secret.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type DrugRequestStatus = "PENDING" | "APPROVED" | "REJECTED";

export type DrugRequest = {
  id: string;
  requested_by_doctor_id: string;
  ten_thuoc: string;
  dang_thuoc: string;
  duong_dung: string;
  ham_luong: string | null;
  tong_so_luong: string | null;
  ly_do: string | null;
  status: DrugRequestStatus;
  reviewed_by_account_id: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  // Gia tri dung lam `drugId` khi ke don, chi co sau khi duyet.
  approved_drug_id: string | null;
  created_at: string;
};

export type DrugRequestInput = {
  tenThuoc: string;
  dangThuoc: string;
  duongDung: string;
  hamLuong?: string;
  tongSoLuong?: string;
  lyDo?: string;
};

function headers(accessToken?: string | null): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };
}

async function doc(response: Response) {
  if (response.ok) return response.json();
  const body = await response.json().catch(() => null);
  // Backend tra loi theo api-contracts.md §10: { error: { code, message } }.
  // Giu nguyen `message` tieng Viet cua backend thay vi thay bang cau chung -
  // vd truong hop chat bi kiem soat, cau do noi ro vuong o hoat chat nao.
  const message =
    body?.detail?.message ??
    (typeof body?.detail === "string" ? body.detail : null) ??
    `Không thực hiện được (${response.status})`;
  throw new Error(message);
}

export async function createDrugRequest(
  input: DrugRequestInput,
  accessToken?: string | null,
): Promise<DrugRequest> {
  return doc(
    await fetch(`${API_BASE}/api/v1/drug-requests`, {
      method: "POST",
      headers: headers(accessToken),
      body: JSON.stringify({
        ten_thuoc: input.tenThuoc,
        dang_thuoc: input.dangThuoc,
        duong_dung: input.duongDung,
        ham_luong: input.hamLuong || undefined,
        tong_so_luong: input.tongSoLuong || undefined,
        ly_do: input.lyDo || undefined,
      }),
    }),
  );
}

/** Yeu cau cua CHINH bac si dang dang nhap - backend loc theo JWT. */
export async function listMyDrugRequests(
  status?: DrugRequestStatus,
  accessToken?: string | null,
): Promise<DrugRequest[]> {
  const qs = status ? `?status=${status}` : "";
  const data = await doc(
    await fetch(`${API_BASE}/api/v1/drug-requests${qs}`, { headers: headers(accessToken) }),
  );
  return data.items;
}

export async function listAllDrugRequests(
  status?: DrugRequestStatus,
  accessToken?: string | null,
): Promise<DrugRequest[]> {
  const qs = status ? `?status=${status}` : "";
  const data = await doc(
    await fetch(`${API_BASE}/api/v1/admin/drug-requests${qs}`, { headers: headers(accessToken) }),
  );
  return data.items;
}

export async function approveDrugRequest(
  id: string,
  note: string | undefined,
  accessToken?: string | null,
): Promise<DrugRequest> {
  return doc(
    await fetch(`${API_BASE}/api/v1/admin/drug-requests/${id}/approve`, {
      method: "POST",
      headers: headers(accessToken),
      body: JSON.stringify({ note: note || undefined }),
    }),
  );
}

export async function rejectDrugRequest(
  id: string,
  note: string,
  accessToken?: string | null,
): Promise<DrugRequest> {
  return doc(
    await fetch(`${API_BASE}/api/v1/admin/drug-requests/${id}/reject`, {
      method: "POST",
      headers: headers(accessToken),
      body: JSON.stringify({ note }),
    }),
  );
}
