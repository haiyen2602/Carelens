"use client";

// Khung dien thoai CapyMedi - port tu capyphone.js: renderAccountRow(),
// renderContent(), renderTabBar() + renderSheetAccount().
//
// KHAC ban goc mot cho co y: KHONG ve thanh trang thai gia ("9:41", song,
// pin). Ban goc la anh chup mo phong dien thoai trong canvas thiet ke; day
// la web app chay tren dien thoai that, da co thanh trang thai that cua may.
//
// Thay PhoneShell cho rieng khu vuc /patient - PhoneShell van duoc trang
// dang nhap (app/page.tsx) dung, khong dung toi.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { CapySheet } from "@/components/capy/capy-ui";
import { DoseCallOverlay } from "@/components/capy/dose-call-overlay";
import { NudgeBanner } from "@/components/capy/nudge-banner";
import { useAuth } from "@/lib/auth";
import { daNhac, danhDauDaNhac } from "@/lib/dose-reminder-log";
import { gioHienThi, listDoses } from "@/lib/doses";
import { reportHealthIssue } from "@/lib/escalations";
import { pollUnseenNudges } from "@/lib/nudges";
import {
  getNotificationPermission,
  playDoseAlarmShort,
  playNudgeSound,
  requestNotificationPermission,
  showBrowserNotification,
  type NotificationPermissionState,
} from "@/lib/notifications";
import { useProto } from "@/lib/proto-store";

// Khoang cach giua 2 lan poll GET /nudges/unseen (backend/api/nudge_routes.py)
// - repo chua co ha tang realtime (WebSocket/SSE), 8s la do tre chap nhan
// duoc cho 1 loi nhac nhe (khong phai canh bao cap cuu).
const NUDGE_POLL_MS = 8000;

// Nhac gio uong thuoc: poll GET /doses roi tu so gio o client (du lieu
// scheduled_at da co san, khong can backend day gi). 15s du min cho 3 moc
// cach nhau 15 phut.
const DOSE_POLL_MS = 15000;

// 3 moc nhac leo thang (phut ke tu gio hen). Moc 30 trung dung luc
// window_end sap dong (NUA_CUA_SO=30p, backend/services/scheduling/generator.py).
const MOC_NHAC_LAN_2 = 15;
const MOC_GOI = 30;

// Qua moc nay thi THOI HAN nhac (SUA 2026-08-20: truoc de 24 gio - qua rong,
// bug that: benh nhan Le Van Tam con 1 lieu PENDING tu dem hom truoc (tre
// ~22 tieng, don da het han nhung khong ai doi status thanh MISSED) nen vua
// dang nhap la bung ngay cuoc goi gia lap). Khung xac nhan cua backend chi
// +-30 phut (NUA_CUA_SO, backend/services/scheduling/generator.py) - qua 60
// phut thi lieu do coi nhu da lo, nhac nua khong con y nghia.
const HET_HAN_NHAC_PHUT = 60;

type Banner = {
  id: string;
  callerName: string;
  message: string;
  source: "nudge" | "dose";
};

type CuocGoi = { doseId: string; tenThuoc: string; gioHen: string };

const TABS = [
  { to: "/patient", label: "Hôm nay", icon: "💊", exact: true },
  { to: "/patient/health", label: "Sức khoẻ", icon: "❤️" },
  { to: "/patient/assistant", label: "Capy AI", icon: "💬" },
  { to: "/patient/family", label: "Người thân", icon: "👨‍👩‍👧" },
  { to: "/patient/history", label: "Lịch sử", icon: "📅" },
];

export function CapyShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, accessToken, logout: authLogout } = useAuth();
  const { logout: protoLogout, emergency, setEmergency } = useProto();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [bannerQueue, setBannerQueue] = useState<Banner[]>([]);
  const [cuocGoi, setCuocGoi] = useState<CuocGoi | null>(null);
  const [notifPerm, setNotifPerm] = useState<NotificationPermissionState>("default");
  const activeBanner = bannerQueue[0] ?? null;

  useEffect(() => {
    const current = getNotificationPermission();
    setNotifPerm(current);
    // SUA 2026-08-20: BO tu dong xin quyen luc mount (thu truoc do) - Chrome/
    // Edge coi request KHONG xuat phat truc tiep tu 1 cu click cua nguoi
    // dung la dau hieu spam, am tham chuyen sang "quiet UI" (chi hien 1 icon
    // chuong gach cheo nho o thanh dia chi, KHONG co popup nao) thay vi hoi
    // that - de nguoi dung tuong app khong xin quyen gi ca. Phai giu request
    // gan lien voi 1 click that (nut "Bat thong bao" trong sheet tai khoan
    // ben duoi) thi Chromium moi hien popup day du.
  }, []);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const items = await pollUnseenNudges(accessToken);
        if (cancelled || items.length === 0) return;
        setBannerQueue((q) => [
          ...q,
          ...items.map((n) => ({
            id: n.id,
            callerName: n.caregiverName,
            message: n.message,
            source: "nudge" as const,
          })),
        ]);
      } catch {
        // Bo qua loi 1 vong poll rieng le (vd mat mang thoang qua) - thu lai
        // vong sau, khong lam phien nguoi dung bang toast loi moi 8s.
      }
    };
    poll();
    const timer = setInterval(poll, NUDGE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [accessToken]);

  // Nhac gio uong thuoc, leo thang 3 moc: banner (+0) -> banner (+15) ->
  // cuoc goi gia lap (+30, kem bao nguoi than). Tinh hoan toan o client tu
  // `scheduledAt` da co san - backend khong can day gi.
  const patientId = user?.patient_id;
  useEffect(() => {
    if (!patientId) return;
    let cancelled = false;

    const kiemTra = async () => {
      let doses;
      try {
        doses = await listDoses(patientId);
      } catch {
        return; // cung ly do voi vong poll nudge o tren
      }
      if (cancelled) return;

      const bay_gio = Date.now();

      // GOP theo KHUNG GIO, khong nhac tung lieu mot (SUA 2026-08-20): 2
      // thuoc cua 2 don khac nhau nhung cung hen 21:00 la 2 dong DoseEvent
      // rieng - nhac rieng se thanh 2 chuong lien tiep cho cung 1 lan uong.
      const theoKhungGio = new Map<string, typeof doses>();
      for (const d of doses) {
        if (d.status !== "PENDING") continue;
        const phutQua = (bay_gio - new Date(d.scheduledAt).getTime()) / 60000;
        if (phutQua < 0 || phutQua > HET_HAN_NHAC_PHUT) continue;
        const khung = new Date(d.scheduledAt).toISOString();
        theoKhungGio.set(khung, [...(theoKhungGio.get(khung) ?? []), d]);
      }

      for (const [khung, nhomLieu] of theoKhungGio) {
        const phutQua = (bay_gio - new Date(khung).getTime()) / 60000;
        const moc = phutQua >= MOC_GOI ? MOC_GOI : phutQua >= MOC_NHAC_LAN_2 ? MOC_NHAC_LAN_2 : 0;
        const khoa = `${khung}:${moc}`;
        // Da nhac o lan mo app truoc thi thoi - localStorage, khong phai bo
        // nho tam: reload/F5 KHONG duoc lam benh nhan bi nhac lai tu dau.
        if (daNhac(khoa)) continue;
        danhDauDaNhac(khoa);

        const tenThuoc = nhomLieu.map((d) => d.expectedItems[0]?.tenThuoc ?? "thuốc").join(" và ");
        const gioHen = gioHienThi(khung);

        if (moc === MOC_GOI) {
          setCuocGoi({ doseId: khung, tenThuoc, gioHen });
          if (accessToken) {
            // Bao nguoi than qua dung he thong Escalation da co (POST
            // /health-log, level "mid" -> severity MEDIUM) - khong doi het
            // khung 60 phut moi bao. .catch nuot loi: cuoc goi gia lap van
            // phai hien du API loi.
            reportHealthIssue(accessToken, {
              text: `Chưa xác nhận uống ${tenThuoc} (hẹn ${gioHen}) sau 3 lần nhắc`,
              level: "mid",
            }).catch(() => {});
          }
        } else {
          setBannerQueue((q) => [
            ...q,
            {
              id: khoa,
              callerName: "Nhắc uống thuốc",
              message:
                moc === 0
                  ? `Đến giờ uống ${tenThuoc} rồi nhé`
                  : `Vẫn chưa thấy bạn xác nhận uống ${tenThuoc}`,
              source: "dose",
            },
          ]);
        }
      }
    };

    kiemTra();
    const timer = setInterval(kiemTra, DOSE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [patientId, accessToken]);

  useEffect(() => {
    if (!activeBanner) return;
    // Neu da co quyen Notification that, chi can no la du (co the tu keo
    // theo tieng cua chinh he dieu hanh) - phat THEM tieng trong app se
    // thanh bao 2 lan cho 1 lan nhac. Chi phat tieng trong app khi CHUA co
    // quyen (patient chua bat/tu choi) - do la kenh am thanh duy nhat ho co.
    if (getNotificationPermission() === "granted") {
      showBrowserNotification("CapyMedi", `${activeBanner.callerName}: ${activeBanner.message}`);
    } else if (activeBanner.source === "dose") {
      playDoseAlarmShort();
    } else {
      playNudgeSound();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeBanner?.id]);

  const doLogout = async () => {
    setSheetOpen(false);
    await authLogout();
    protoLogout();
    router.push("/login");
  };

  const ten = user?.full_name ?? "";
  const chuDau = ten.charAt(0).toUpperCase();
  const tenNgan = ten.trim().split(/\s+/).pop() ?? ten;

  return (
    <div className="h-dvh bg-[#E9E9EF] px-0 py-0 sm:px-4 sm:py-8">
      <div className="relative mx-auto flex h-full w-full max-w-[430px] flex-col overflow-hidden bg-[#F1F1F6] sm:h-[min(860px,calc(100dvh-4rem))] sm:rounded-[46px] sm:shadow-[0_26px_60px_rgba(22,56,110,.24)]">
        {/* Hang tai khoan */}
        <div className="flex shrink-0 justify-end px-5 pb-0 pt-3">
          <button
            onClick={() => setSheetOpen(true)}
            aria-label="Tài khoản của bạn"
            className="flex items-center gap-2 rounded-full bg-white py-[5px] pl-[6px] pr-3 transition-colors hover:bg-[#F4F7FC]"
          >
            <span className="font-display grid h-[30px] w-[30px] place-items-center rounded-full bg-[#CFE6FF] text-[14px] font-bold text-[#16386E]">
              {chuDau}
            </span>
            <span className="text-[12px] font-semibold text-[#16386E]">{tenNgan}</span>
            <span className="font-mono text-[10px] text-[#62708A]">▾</span>
          </button>
        </div>

        {/* Noi dung tab */}
        <main className="capy-scroll min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-5 pb-6 pt-2">
          {children}
        </main>

        {/* Thanh tab */}
        <nav className="grid shrink-0 grid-cols-5 gap-1 border-t border-[#E7EBF3] bg-white px-3 pb-[22px] pt-2.5">
          {TABS.map((t) => {
            const active = t.exact ? pathname === t.to : pathname.startsWith(t.to);
            return (
              <Link
                key={t.to}
                href={t.to}
                className="flex min-h-[44px] flex-col items-center gap-[5px] rounded-[14px] px-0.5 py-[5px]"
              >
                <span
                  className="h-[6px] w-[22px] rounded-full"
                  style={{ background: active ? "#16386E" : "transparent" }}
                />
                <span
                  aria-hidden="true"
                  className="text-[19px] leading-none"
                  style={{ opacity: active ? 1 : 0.5 }}
                >
                  {t.icon}
                </span>
                <span
                  className="whitespace-nowrap text-[11px] font-semibold"
                  style={{ color: active ? "#16386E" : "#62708A" }}
                >
                  {t.label}
                </span>
              </Link>
            );
          })}
        </nav>

        {sheetOpen && (
          <CapySheet onClose={() => setSheetOpen(false)}>
            <div className="flex items-center gap-3.5">
              <span className="font-display grid h-14 w-14 place-items-center rounded-[20px] bg-[#CFE6FF] text-[22px] font-bold text-[#16386E]">
                {chuDau}
              </span>
              <span className="block min-w-0">
                <span className="font-display block text-[20px] font-extrabold text-[#16386E]">
                  {ten}
                </span>
                {user?.patient_id && (
                  <span className="font-mono block text-[11px] text-[#62708A]">
                    {user.patient_id}
                  </span>
                )}
              </span>
            </div>

            <div className="mt-[18px] flex flex-col gap-2">
              <Link
                href="/patient/settings"
                onClick={() => setSheetOpen(false)}
                className="flex min-h-[54px] items-center gap-3 rounded-[18px] bg-[#F4F7FC] px-4 text-[14.5px] font-semibold text-[#1B2A44] transition-colors hover:bg-[#EDF0F6]"
              >
                <span aria-hidden="true" className="text-[18px]">
                  🧑
                </span>
                Chỉnh sửa thông tin
                <span className="font-mono ml-auto text-[12px] text-[#62708A]">›</span>
              </Link>
              <button
                onClick={async () => {
                  if (notifPerm === "denied") {
                    toast("Bạn đã từ chối nhận thông báo — mở cài đặt trình duyệt để bật lại");
                    return;
                  }
                  const result = await requestNotificationPermission();
                  setNotifPerm(result);
                  if (result === "granted") toast.success("Đã bật thông báo");
                  else if (result === "denied") toast("Bạn đã từ chối nhận thông báo");
                }}
                className="flex min-h-[54px] items-center gap-3 rounded-[18px] bg-[#F4F7FC] px-4 text-[14.5px] font-semibold text-[#1B2A44] transition-colors hover:bg-[#EDF0F6]"
              >
                <span aria-hidden="true" className="text-[18px]">
                  🔔
                </span>
                {notifPerm === "granted"
                  ? "Đã bật thông báo"
                  : notifPerm === "denied"
                    ? "Thông báo: đã từ chối"
                    : "Bật thông báo"}
                <span className="font-mono ml-auto text-[12px] text-[#62708A]">›</span>
              </button>
              <Link
                href="/patient/family"
                onClick={() => setSheetOpen(false)}
                className="flex min-h-[54px] items-center gap-3 rounded-[18px] bg-[#F4F7FC] px-4 text-[14.5px] font-semibold text-[#1B2A44] transition-colors hover:bg-[#EDF0F6]"
              >
                <span aria-hidden="true" className="text-[18px]">
                  🔒
                </span>
                Quyền &amp; chia sẻ
                <span className="font-mono ml-auto text-[12px] text-[#62708A]">›</span>
              </Link>
            </div>

            <div className="mt-4 flex gap-2.5">
              <button
                onClick={() => setSheetOpen(false)}
                className="flex min-h-[52px] flex-1 items-center justify-center rounded-[18px] bg-[#EDF0F6] text-[15px] font-semibold text-[#1B2A44] transition-colors hover:bg-[#E3E8F1]"
              >
                Đóng
              </button>
              <button
                onClick={doLogout}
                className="flex min-h-[52px] flex-1 items-center justify-center rounded-[18px] bg-[#F6E9E7] text-[15px] font-bold text-[#B4432C] transition-colors hover:bg-[#F2DDD9]"
              >
                Đăng xuất
              </button>
            </div>
          </CapySheet>
        )}

        {emergency && (
          <div className="absolute inset-0 z-[60] flex flex-col items-center justify-center gap-5 bg-[#E23B33] p-8 text-center text-white">
            <h2 className="font-display text-3xl font-extrabold">Cảnh báo cấp cứu</h2>
            <p className="max-w-sm">
              Dấu hiệu nguy hiểm được phát hiện. Hãy gọi ngay 115 hoặc để người thân hỗ trợ bạn.
            </p>
            <a
              href="tel:115"
              className="font-display flex items-center gap-2 rounded-full bg-white px-8 py-4 text-lg font-extrabold text-[#E23B33]"
            >
              📞 Gọi 115
            </a>
            <button className="text-white/90 underline" onClick={() => setEmergency(false)}>
              Đóng overlay
            </button>
          </div>
        )}

        {activeBanner && (
          <NudgeBanner
            key={activeBanner.id}
            callerName={activeBanner.callerName}
            message={activeBanner.message}
            onDismiss={() => setBannerQueue((q) => q.slice(1))}
          />
        )}

        {cuocGoi && (
          <DoseCallOverlay
            key={cuocGoi.doseId}
            tenThuoc={cuocGoi.tenThuoc}
            gioHen={cuocGoi.gioHen}
            onClose={() => setCuocGoi(null)}
          />
        )}
      </div>
    </div>
  );
}
