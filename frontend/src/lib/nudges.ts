// Loi nhac nhe nguoi than gui cho benh nhan (backend/api/nudge_routes.py) -
// goi THANG backend kem Bearer, cung mau voi cac ham invite/accept trong
// lib/caregivers.ts (khong qua route noi bo /api/* cua chinh FE).

export type Nudge = {
  id: string;
  caregiverAccountId: string;
  caregiverName: string;
  patientId: string;
  message: string;
  createdAt: string;
};

type NudgeApi = {
  id: string;
  caregiver_account_id: string;
  caregiver_name: string;
  patient_id: string;
  message: string;
  created_at: string;
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

function toNudge(n: NudgeApi): Nudge {
  return {
    id: n.id,
    caregiverAccountId: n.caregiver_account_id,
    caregiverName: n.caregiver_name,
    patientId: n.patient_id,
    message: n.message,
    createdAt: n.created_at,
  };
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Nguoi than dang dang nhap gui 1 loi nhac cho benh nhan ho dang theo doi
 * (accepted) - backend tu kiem tra lien ket, 403 neu chua theo doi. */
export async function sendNudge(
  accessToken: string,
  input: { patientId: string; message: string },
): Promise<Nudge> {
  const response = await fetch(`${API_BASE}/api/v1/nudges`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ patient_id: input.patientId, message: input.message }),
  });
  if (!response.ok) return loi(response);
  return toNudge(await response.json());
}

/** Benh nhan poll dinh ky - moi nhac tra ve bi backend danh dau seen NGAY
 * trong request nay (khong tra lai lan poll sau), xem ghi chu trong
 * backend/api/nudge_routes.py. */
export async function pollUnseenNudges(accessToken: string): Promise<Nudge[]> {
  const response = await fetch(`${API_BASE}/api/v1/nudges/unseen`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) return loi(response);
  const items: NudgeApi[] = await response.json();
  return items.map(toNudge);
}
