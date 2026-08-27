// Ghep tai khoan Telegram de nhan nhac gio uong thuoc (THEM 2026-08-27).
//
// Khac han lib/push.ts o MOT diem quyet dinh: Web Push dang ky duoc hoan toan
// ngam trong nen (chi can quyen Notification), con Telegram BAT BUOC benh
// nhan roi khoi app mot lan - bam vao link t.me, bam Start voi bot. Khong co
// cach nao lam thay ho: Bot API cua Telegram khong gui duoc tin theo so dien
// thoai/email, chat_id chi sinh ra khi chinh ho bam Start (xem
// backend/services/telegram.py).
//
// MOI ham deu nuot loi thay vi throw, cung ly do voi push.ts: Telegram la
// kenh PHU, server chua cau hinh bot hay mang loi deu KHONG duoc lam vo man
// hinh cai dat.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TelegramStatus = {
  /** false = server chua cau hinh bot -> an han tinh nang di, dung hien nut
   * bam vao roi bao loi. */
  configured: boolean;
  linked: boolean;
  username: string | null;
  /** TACH BIET voi `linked`: da noi tai khoan nhung tam tat nhac la trang
   * thai hop le - hien cong tac o vi tri tat, KHONG quay ve nut "Kết nối". */
  enabled: boolean;
};

const TAT = { configured: false, linked: false, username: null, enabled: false } as const;

export async function getTelegramStatus(accessToken: string): Promise<TelegramStatus> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/telegram/status`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) return { ...TAT };
    return (await response.json()) as TelegramStatus;
  } catch {
    return { ...TAT };
  }
}

/** Xin link ghep roi mo Telegram. Tra ve false neu khong lay duoc link.
 *
 * MO TAB TRONG TRUOC KHI await bat ky thu gi, roi moi tro no sang deep link.
 * Cach hien nhien hon (await fetch xong moi window.open) BI CHAN tren Safari
 * va Safari iOS: hai trinh duyet do chi cho mo tab trong dung luot bam cua
 * nguoi dung, ma sau mot await thi luot bam do da ket thuc. Benh nhan iOS
 * lai chinh la nhom can kenh Telegram nhat - Web Push tren iOS doi phai cai
 * PWA ra man hinh chinh, thu phan lon nguoi cao tuoi khong bao gio lam.
 *
 * KHONG dat "noopener" trong window.open: co no thi ham tra ve null, mat
 * luon cai handle can de tro location. Thay bang gan opener = null ngay sau
 * do - cung tac dung chan trang moi truy nguoc window.opener. */
export async function batDauGhepTelegram(accessToken: string): Promise<boolean> {
  const tab = window.open("", "_blank");
  if (tab) tab.opener = null;
  try {
    const response = await fetch(`${API_BASE}/api/v1/telegram/link-token`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) {
      tab?.close();
      return false;
    }
    const { deep_link: deepLink } = await response.json();
    if (!deepLink) {
      tab?.close();
      return false;
    }
    if (tab) {
      tab.location.href = deepLink;
    } else {
      // Trinh duyet van chan tab trong (vd cai chan popup rat chat) - thu
      // not cach thang, thua con hon khong mo duoc gi.
      window.open(deepLink, "_blank", "noopener,noreferrer");
    }
    return true;
  } catch {
    tab?.close();
    return false;
  }
}

/** Bat/tat nhac Telegram ma VAN giu lien ket - bat lai chi la 1 cu gat,
 * khong phai lam lai ca luong ghep nhu sau khi goKetNoiTelegram(). */
export async function datTuyChonTelegram(accessToken: string, enabled: boolean): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/telegram/link`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ enabled }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function goKetNoiTelegram(accessToken: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/telegram/link`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    return response.ok;
  } catch {
    return false;
  }
}
