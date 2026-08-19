"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search } from "lucide-react";

// Select danh sach co dinh (khac combobox tim/go) - mo khi ruot chuot vao
// (cung UX voi menu tai khoan o doctor/layout.tsx), khong dung Radix Select
// vi mo/dong theo hover se xung dot voi co che focus/click cua Radix.
export type HoverSelectOption = { value: string; label: string };

// Tren nguong nay moi hien o loc trong dropdown. Duoi nguong, cuon mat vai
// dong la thay het - them o go chi lam roi mat.
const NGUONG_HIEN_O_LOC = 10;

// Bo dau de go khong dau van tim duoc ("bot pha" -> "Bột pha dung dịch uống").
// Cung tinh than voi unaccent() ben backend (services/drug_knowledge).
// NFD khong tach duoc "đ" nen phai thay tay.
const DAU_KET_HOP = /\p{Diacritic}/gu;

function boDau(s: string): string {
  return s
    .normalize("NFD")
    .replace(DAU_KET_HOP, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
}

export function HoverSelect({
  id,
  value,
  onChange,
  options,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: HoverSelectOption[];
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const inputRef = useRef<HTMLInputElement>(null);

  const coOLoc = options.length > NGUONG_HIEN_O_LOC;

  const openNow = () => {
    clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const scheduleClose = () => {
    closeTimer.current = setTimeout(() => setOpen(false), 150);
  };

  // Moi lan mo lai thi bat dau tu danh sach day du, khong giu tu khoa cu.
  useEffect(() => {
    if (open) {
      if (coOLoc) inputRef.current?.focus();
    } else {
      setQ("");
    }
  }, [open, coOLoc]);

  const selectedLabel = options.find((o) => o.value === value)?.label ?? "";

  const hienThi = useMemo(() => {
    const tuKhoa = boDau(q.trim());
    if (!tuKhoa) return options;
    return options.filter((o) => boDau(o.label).includes(tuKhoa));
  }, [options, q]);

  return (
    <div className="relative" onMouseEnter={openNow} onMouseLeave={scheduleClose}>
      <button
        id={id}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 w-full items-center justify-between rounded-xl border border-input bg-card px-3 text-sm outline-none focus:border-primary"
      >
        <span className="truncate">{selectedLabel}</span>
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div
          className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-border bg-card shadow-lg"
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
        >
          {coOLoc && (
            <div className="relative border-b border-border p-2">
              <Search
                aria-hidden="true"
                className="absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
              />
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Lọc…"
                aria-label="Lọc danh sách"
                className="h-8 w-full rounded-md border border-input bg-background pl-7 pr-2 text-sm outline-none focus:border-primary"
              />
            </div>
          )}

          {/* max-h + cuon doc: danh sach co the rat dai (vd bo loc "dang bao
              che" o trang tra cuu thuoc co hang tram gia tri lay tu DB).
              Danh sach ngan khong bi anh huong - max-h chi co tac dung khi
              vuot qua. */}
          <div className="max-h-64 overflow-y-auto overscroll-contain py-1">
            {hienThi.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <span className="truncate">{o.label}</span>
                {o.value === value && <Check className="h-4 w-4 shrink-0 text-primary" />}
              </button>
            ))}
            {hienThi.length === 0 && (
              <p className="px-3 py-4 text-center text-sm text-muted-foreground">
                Không có mục nào khớp.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
