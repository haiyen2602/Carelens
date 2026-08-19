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
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { CapySheet } from "@/components/capy/capy-ui";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

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
  const { user, logout: authLogout } = useAuth();
  const { logout: protoLogout, emergency, setEmergency } = useProto();
  const [sheetOpen, setSheetOpen] = useState(false);

  const doLogout = async () => {
    setSheetOpen(false);
    await authLogout();
    protoLogout();
    router.push("/");
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
                onClick={() => toast("Cài đặt nhắc nhở chưa nối API — sắp có")}
                className="flex min-h-[54px] items-center gap-3 rounded-[18px] bg-[#F4F7FC] px-4 text-[14.5px] font-semibold text-[#1B2A44] transition-colors hover:bg-[#EDF0F6]"
              >
                <span aria-hidden="true" className="text-[18px]">
                  🔔
                </span>
                Cài đặt nhắc nhở
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
      </div>
    </div>
  );
}
