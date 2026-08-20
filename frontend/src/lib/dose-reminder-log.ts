// Ghi nho "moc nhac nao da ban roi" cho tung khung gio uong thuoc, LUU BEN
// (localStorage) chu khong phai trong RAM.
//
// Vi sao khong dung useRef nhu ban dau (SUA 2026-08-20): ref chi song trong
// 1 lan mount cua trang. Reload/F5, hot-reload luc dev, hay benh nhan dong
// mo lai app deu xoa sach -> MOI lieu qua gio bi nhac lai tu dau, benh nhan
// nghe chuong lien tuc du da xem roi. Day la bug that tren may that, khong
// chi la hien tuong luc dev.
//
// KHONG dung sessionStorage: no cung mat khi dong tab, dung y muon o day la
// "da nhac roi thi thoi, ke ca mo lai app".

const KHOA = "capymedi:dose-reminder-log";

// Don cac ban ghi cu hon nguong nay moi lan doc - lieu qua 24h khong con
// duoc nhac nua (xem QUA_CU_PHUT o capy-shell.tsx) nen giu lai vo ich, de
// lau se phinh localStorage.
const GIU_LAI_MS = 36 * 60 * 60 * 1000;

type BanGhi = Record<string, number>; // "{khoaKhungGio}:{moc}" -> timestamp da ban

function doc(): BanGhi {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(KHOA);
    if (!raw) return {};
    const data = JSON.parse(raw) as BanGhi;
    const nguong = Date.now() - GIU_LAI_MS;
    return Object.fromEntries(Object.entries(data).filter(([, at]) => at >= nguong));
  } catch {
    // localStorage bi chan (che do rieng tu cua vai trinh duyet) hoac du
    // lieu hong - coi nhu chua nhac gi, khong lam vo ca man hinh.
    return {};
  }
}

function ghi(data: BanGhi): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KHOA, JSON.stringify(data));
  } catch {
    // Het dung luong / bi chan - bo qua, cung lam la nhac lai 1 lan thua.
  }
}

export function daNhac(khoa: string): boolean {
  return khoa in doc();
}

export function danhDauDaNhac(khoa: string): void {
  const data = doc();
  data[khoa] = Date.now();
  ghi(data);
}
