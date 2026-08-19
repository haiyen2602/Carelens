// Xin quyen Notification thuc cua trinh duyet + phat am thanh cho banner
// nhac nho trong app (components/capy/nudge-banner.tsx). 2 co che DOC LAP
// nhau: Notification that KHONG con ho tro tuy chinh am thanh (option
// `sound` da bi bo khoi spec) - am thanh o day chi gan voi banner tu ve
// trong app, phat qua the <audio>, khong lien quan gi den quyen Notification.

export type NotificationPermissionState = "granted" | "denied" | "default" | "unsupported";

export function getNotificationPermission(): NotificationPermissionState {
  if (typeof window === "undefined" || !("Notification" in window)) return "unsupported";
  return Notification.permission;
}

export async function requestNotificationPermission(): Promise<NotificationPermissionState> {
  if (typeof window === "undefined" || !("Notification" in window)) return "unsupported";
  // Trinh duyet chi cho hoi 1 lan - sau khi "denied", goi lai ham nay se tra
  // ve "denied" ngay khong hien popup nua (hanh vi cua chinh trinh duyet,
  // khong can tu luu flag "da hoi" rieng).
  const result = await Notification.requestPermission();
  return result;
}

/** Bao gio hien Notification that (chi khi da granted VA tab dang mo - repo
 * chua co Service Worker/Web Push nen khong the goi khi app da dong). */
export function showBrowserNotification(title: string, body: string): void {
  if (getNotificationPermission() !== "granted") return;
  try {
    new Notification(title, { body });
  } catch {
    // Mot so trinh duyet (Safari cu, may khong ho tro) van co the nem loi
    // du permission = granted - banner trong app la du, khong throw tiep.
  }
}

let cachedAudio: HTMLAudioElement | null = null;

/** Phat tieng "notice.wav" khi banner nhac nho hien ra. Boc try/catch nuot
 * loi autoplay-block cua trinh duyet (vd tab chua tung co tuong tac nguoi
 * dung) - khong phat duoc tieng thi banner van hien binh thuong. */
export function playNudgeSound(): void {
  if (typeof window === "undefined") return;
  try {
    if (!cachedAudio) cachedAudio = new Audio("/sounds/notice.wav");
    cachedAudio.currentTime = 0;
    void cachedAudio.play().catch(() => {});
  } catch {
    // Nuot loi co y - am thanh la phu, khong lam hong trai nghiem banner.
  }
}
