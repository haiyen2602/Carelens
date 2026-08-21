// Dang ky nhan Web Push (THEM 2026-08-20).
//
// Khac han lib/notifications.ts: ham o day lo phan nhan thong bao khi app DA
// DONG HAN (qua Service Worker + day tu server), con notifications.ts lo
// thong bao/am thanh trong luc tab dang mo. 2 lop doc lap, dung chung 1
// quyen Notification cua trinh duyet.
//
// MOI ham deu nuot loi thay vi throw: push la tinh nang PHU. Trinh duyet
// khong ho tro Push API, chua cau hinh VAPID phia server, hay nguoi dung
// chan quyen - tat ca deu KHONG duoc lam vo luong xin quyen Notification von
// dang chay tot (banner + tieng trong app van hoat dong binh thuong).

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** VAPID public key tu server la base64url, con pushManager.subscribe() doi
 * Uint8Array - phai tu chuyen, khong co API san. */
function base64UrlToUint8Array(base64Url: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  // Cap phat ArrayBuffer tuong minh thay vi `new Uint8Array(length)`: kieu
  // BufferSource cua applicationServerKey doi dung Uint8Array<ArrayBuffer>,
  // con dang ngan gon kia ra Uint8Array<ArrayBufferLike> (co the la
  // SharedArrayBuffer) nen TypeScript tu choi.
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** Dang ky thiet bi hien tai de nhan nhac uong thuoc ke ca khi app da dong.
 * Tra ve true neu dang ky duoc that. Goi SAU khi quyen Notification da
 * "granted" - subscribe() se tu that bai neu chua co quyen. */
export async function subscribeToPush(accessToken: string): Promise<boolean> {
  if (!pushSupported()) return false;

  try {
    const keyResponse = await fetch(`${API_BASE}/api/v1/push/vapid-public-key`);
    if (!keyResponse.ok) return false;
    const { public_key: publicKey } = await keyResponse.json();
    // Server chua cau hinh VAPID - im lang bo qua, dung bao loi cho nguoi
    // dung ve 1 thu ho khong dat duoc (xem backend/services/push.py).
    if (!publicKey) return false;

    const registration = await navigator.serviceWorker.register("/sw.js");
    // Cho SW san sang han: subscribe() ngay sau register() co the chay khi
    // SW con "installing" va bi tu choi.
    await navigator.serviceWorker.ready;

    // Da dang ky tu truoc (vd lan mo app truoc) thi dung lai dung subscription
    // do - tao moi se lam endpoint cu thanh rac trong bang push_subscription.
    const existing = await registration.pushManager.getSubscription();
    const subscription =
      existing ??
      (await registration.pushManager.subscribe({
        // Bat buoc true tren Chrome: cam ket moi lan nhan push deu hien 1
        // thong bao cho nguoi dung thay (xem ghi chu trong public/sw.js).
        userVisibleOnly: true,
        applicationServerKey: base64UrlToUint8Array(publicKey),
      }));

    const json = subscription.toJSON();
    const response = await fetch(`${API_BASE}/api/v1/push/subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/** Da co subscription tren may nay chua - dung de client biet co nen thoi tu
 * ban Notification he thong hay khong (tranh bao 2 lan cho 1 lieu). */
export async function hasPushSubscription(): Promise<boolean> {
  if (!pushSupported()) return false;
  try {
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) return false;
    return (await registration.pushManager.getSubscription()) !== null;
  } catch {
    return false;
  }
}
