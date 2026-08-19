"use client";

// Banner mo phong thong bao he thong ("push notification") khi nguoi than
// gui loi nhac qua sheet "Nhac nhe" (patient/family/page.tsx). Dat absolute
// trong khung dien thoai (CapyShell), TU DONG an sau AUTO_DISMISS_MS - khac
// CapySheet (can nguoi dung tu dong, khong tu bien mat).

import Image from "next/image";
import { useEffect, useState } from "react";
import { X } from "lucide-react";

const AUTO_DISMISS_MS = 4500;
const EXIT_ANIMATION_MS = 300;

export function NudgeBanner({
  callerName,
  message,
  onDismiss,
}: {
  callerName: string;
  message: string;
  onDismiss: () => void;
}) {
  // 3 trang thai thay vi 1 boolean - SUA 2026-08-20: ban cu dung 1 boolean
  // `visible` bi RACE khi tab dang o nen (vd nguoi dung dang o tab khac luc
  // nhac den): requestAnimationFrame() BI TAM DUNG hoan toan khi tab an
  // (spec, khong chi bi throttle nhu setTimeout), nen hieu ung "vao" khong
  // bao gio chay - nhung effect "thoat" van doc duoc `visible === false`
  // (gia tri KHOI TAO, chua kip doi thanh true) ngay lan render dau, tuong
  // banner da an nen goi onDismiss() sau 300ms - xoa banner khoi hang doi
  // truoc khi nguoi dung quay lai tab de thay no. Dung 3 pha ro rang: chi
  // bat dau dem gio tu-an SAU KHI thuc su vao trang thai "visible" (tuc SAU
  // khi rAF thuc su chay), nen neu tab dang an thi banner cu treo o
  // "entering" cho toi khi nguoi dung quay lai - dung y (khong ai muon tu
  // dong bien mat 1 thu ho chua tung thay).
  const [phase, setPhase] = useState<"entering" | "visible" | "exiting">("entering");
  const shown = phase === "visible";

  useEffect(() => {
    const raf = requestAnimationFrame(() => setPhase("visible"));
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    if (phase !== "visible") return;
    const autoHide = setTimeout(() => setPhase("exiting"), AUTO_DISMISS_MS);
    return () => clearTimeout(autoHide);
  }, [phase]);

  useEffect(() => {
    if (phase !== "exiting") return;
    // Cho hieu ung truot len chay xong roi moi thao banner khoi DOM (goi
    // onDismiss) - tranh cat cut animation.
    const timer = setTimeout(onDismiss, EXIT_ANIMATION_MS);
    return () => clearTimeout(timer);
  }, [phase, onDismiss]);

  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-[55] flex justify-center px-3 pt-3">
      <button
        type="button"
        onClick={() => setPhase("exiting")}
        aria-label={`Đóng thông báo: ${message}`}
        className="pointer-events-auto flex w-full max-w-[380px] items-start gap-3 rounded-[20px] bg-white/95 p-3 text-left shadow-[0_12px_32px_rgba(22,56,110,.28)] backdrop-blur transition-all duration-300 ease-out"
        style={{
          transform: shown ? "translateY(0)" : "translateY(-120%)",
          opacity: shown ? 1 : 0,
        }}
      >
        <span className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-full bg-[#CFE6FF]">
          <Image src="/capy_nhacnho.png" alt="" width={44} height={44} className="object-cover" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="font-display truncate text-[12px] font-bold uppercase tracking-[0.04em] text-[#62708A]">
              CapyMedi · {callerName}
            </span>
          </span>
          <span className="font-display mt-0.5 block text-[14.5px] font-bold leading-[1.3] text-[#16386E]">
            Nhắc nhở
          </span>
          <span className="mt-0.5 block text-[13px] leading-[1.4] text-[#3A4A66]">{message}</span>
        </span>
        <X className="mt-0.5 h-4 w-4 shrink-0 text-[#9AA6BC]" aria-hidden="true" />
      </button>
    </div>
  );
}
