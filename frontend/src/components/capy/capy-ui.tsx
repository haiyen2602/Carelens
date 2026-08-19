"use client";

// Cac manh giao dien dung chung, port 1:1 tu "CapyMedi App/capyphone.js"
// (pillChip(), overlay(), sheetHandle(), cac khoi label/card lap lai nhieu
// lan trong renderToday/renderHealth/renderFamily/renderHistory).
//
// Mau/kich thuoc de nguyen dang hex + px nhu ban goc: day la ban port co y
// bam sat thiet ke, khong phai code moi suy ra tu design token.

import type { ReactNode } from "react";

/* ---------------------------------------------------------------- *
 * Chip trang thai lieu thuoc (CHIP trong ban goc)
 * ---------------------------------------------------------------- */

export type ChipStyle = { label: string; icon: string; bg: string; fg: string };

export const CHIP: Record<string, ChipStyle> = {
  taken: { label: "Đã uống", icon: "✓", bg: "#DFF3E9", fg: "#1F6A50" },
  late: { label: "Muộn", icon: "✓", bg: "#DFF3E9", fg: "#1F6A50" },
  upcoming: { label: "Sắp tới", icon: "◦", bg: "#EDF0F6", fg: "#5B6A85" },
  due: { label: "Đến giờ", icon: "●", bg: "#16386E", fg: "#FFFFFF" },
  waiting: { label: "Chờ xác nhận", icon: "◑", bg: "#FDEBC9", fg: "#8A6516" },
  overdue: { label: "Quá giờ", icon: "!", bg: "#F6E1DD", fg: "#B4432C" },
  missed: { label: "Bỏ liều", icon: "✕", bg: "#F6E1DD", fg: "#B4432C" },
  cancelled: { label: "Đã huỷ", icon: "–", bg: "#EDF0F6", fg: "#5B6A85" },
};

/** Trang thai lieu that tu backend -> chip cua ban thiet ke. */
export const CHIP_THEO_TRANG_THAI: Record<string, ChipStyle> = {
  TAKEN: CHIP.taken,
  DELAYED: CHIP.late,
  MISSED: CHIP.missed,
  CANCELLED: CHIP.cancelled,
  AWAITING_CAREGIVER: CHIP.waiting,
  PENDING: CHIP.upcoming,
};

export function PillChip({ chip, className = "" }: { chip: ChipStyle; className?: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-[5px] whitespace-nowrap rounded-full px-2.5 py-[5px] text-[11px] font-bold ${className}`}
      style={{ background: chip.bg, color: chip.fg }}
    >
      {chip.icon} {chip.label}
    </span>
  );
}

/* ---------------------------------------------------------------- *
 * Nhan muc (uppercase, letter-spacing .1em) — lap o ca 4 tab
 * ---------------------------------------------------------------- */

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="m-0 text-[12px] font-bold uppercase tracking-[0.1em] text-[#62708A]">
      {children}
    </p>
  );
}

/* ---------------------------------------------------------------- *
 * Bottom sheet (overlay() + sheetHandle() cua ban goc)
 * ---------------------------------------------------------------- */

export function CapySheet({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  return (
    <div className="absolute inset-0 z-50 flex items-end bg-[rgba(15,26,45,.42)]">
      <div className="absolute inset-0" onClick={onClose} aria-hidden="true" />
      <div className="capy-sheet relative w-full rounded-[32px_32px_46px_46px] bg-white px-5 pb-[30px] pt-[22px]">
        <span className="mx-auto mb-4 block h-[5px] w-11 rounded-full bg-[#E3E8F1]" />
        {children}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- *
 * Nut trong sheet: hang day du, co the kem gio ben phai
 * ---------------------------------------------------------------- */

export function SheetRowButton({
  label,
  meta,
  onClick,
  disabled,
}: {
  label: string;
  meta?: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex min-h-[54px] items-center justify-between rounded-[18px] bg-[#EDF0F6] px-[18px] text-[15px] font-semibold text-[#1B2A44] transition-colors hover:bg-[#E3E8F1] disabled:opacity-50"
    >
      {label}
      {meta && <span className="font-mono text-[12px] text-[#62708A]">{meta}</span>}
    </button>
  );
}

/* ---------------------------------------------------------------- *
 * Nut chinh / phu cua ban thiet ke (khong dung shadcn Button de giu
 * dung kich thuoc + bo goc goc: 56px/20px va 48px/18px)
 * ---------------------------------------------------------------- */

export function CapyPrimaryButton({
  children,
  onClick,
  disabled,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`font-display flex min-h-[56px] w-full items-center justify-center gap-2 rounded-[20px] bg-[#16386E] text-[17px] font-bold text-white transition-colors hover:bg-[#0E2749] active:scale-[.985] disabled:opacity-60 ${className}`}
    >
      {children}
    </button>
  );
}

export function CapySecondaryButton({
  children,
  onClick,
  disabled,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex min-h-[48px] flex-1 items-center justify-center gap-2 rounded-[18px] bg-[#EDF0F6] text-[14px] font-semibold text-[#1B2A44] transition-colors hover:bg-[#E3E8F1] disabled:opacity-60 ${className}`}
    >
      {children}
    </button>
  );
}
