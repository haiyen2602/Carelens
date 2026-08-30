// Tuy chon thong bao cua benh nhan - man hinh Cai dat (THEM 2026-08-27).
//
// HAI TANG, co y tach roi trong ca API lan giao dien:
//   Tang 1  dose_reminder_enabled  - CO muon duoc nhac uong thuoc khong
//   Tang 2  web_push_enabled / telegram_enabled  - nhac qua duong nao
//
// Tat tang 1 thi khong kenh nao gui, du tung kenh van bat. Do la ly do giao
// dien long tang 2 vao BEN TRONG tang 1 - nguoi dung phai nhin ra duoc quan
// he do ma khong can doc giai thich.
//
// MOI ham deu nuot loi thay vi throw, cung ly do voi lib/push.ts va
// lib/telegram.ts: mot loi mang khong duoc lam vo man hinh Cai dat.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type NotificationPrefs = {
  /** HAI CỜ NÀY KHÔNG LOẠI TRỪ NHAU - một người vừa có lịch uống thuốc của
   * chính mình vừa theo dõi bố/mẹ là chuyện bình thường. Đừng suy ra vai trò
   * từ `role` của tài khoản: nó chỉ giữ được một giá trị. */
  isPatient: boolean;
  isCaregiver: boolean;
  doseReminderEnabled: boolean;
  webPushEnabled: boolean;
  /** false = server chua cau hinh bot -> an han muc Telegram di. */
  telegramConfigured: boolean;
  telegramLinked: boolean;
  telegramEnabled: boolean;
  telegramUsername: string | null;
};

type ApiShape = {
  is_patient: boolean;
  is_caregiver: boolean;
  dose_reminder_enabled: boolean;
  web_push_enabled: boolean;
  telegram_configured: boolean;
  telegram_linked: boolean;
  telegram_enabled: boolean;
  telegram_username: string | null;
};

function doiSangClient(raw: ApiShape): NotificationPrefs {
  return {
    isPatient: raw.is_patient,
    isCaregiver: raw.is_caregiver,
    doseReminderEnabled: raw.dose_reminder_enabled,
    webPushEnabled: raw.web_push_enabled,
    telegramConfigured: raw.telegram_configured,
    telegramLinked: raw.telegram_linked,
    telegramEnabled: raw.telegram_enabled,
    telegramUsername: raw.telegram_username,
  };
}

export async function getNotificationPrefs(accessToken: string): Promise<NotificationPrefs | null> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/notifications/preferences`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) return null;
    return doiSangClient((await response.json()) as ApiShape);
  } catch {
    return null;
  }
}

/** Chi gui truong CAN doi, khong gui ca cum: benh nhan gat 1 cong tac tai 1
 * thoi diem, gui ca cum se ghi de nham gia tri cong tac kia neu ho dang mo
 * 2 tab. Tra ve trang thai SAU khi doi de goi 1 vong la du. */
export async function setNotificationPrefs(
  accessToken: string,
  thayDoi: { doseReminderEnabled?: boolean; webPushEnabled?: boolean },
): Promise<NotificationPrefs | null> {
  const body: Record<string, boolean> = {};
  if (thayDoi.doseReminderEnabled !== undefined) {
    body.dose_reminder_enabled = thayDoi.doseReminderEnabled;
  }
  if (thayDoi.webPushEnabled !== undefined) body.web_push_enabled = thayDoi.webPushEnabled;

  try {
    const response = await fetch(`${API_BASE}/api/v1/notifications/preferences`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify(body),
    });
    if (!response.ok) return null;
    return doiSangClient((await response.json()) as ApiShape);
  } catch {
    return null;
  }
}
