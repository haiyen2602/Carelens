"use client";

import { useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

// Select danh sach co dinh (khac combobox tim/go) - mo khi ruot chuot vao
// (cung UX voi menu tai khoan o doctor/layout.tsx), khong dung Radix Select
// vi mo/dong theo hover se xung dot voi co che focus/click cua Radix.
export type HoverSelectOption = { value: string; label: string };

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
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const openNow = () => {
    clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const scheduleClose = () => {
    closeTimer.current = setTimeout(() => setOpen(false), 150);
  };

  const selectedLabel = options.find((o) => o.value === value)?.label ?? "";

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
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-border bg-card py-1 shadow-lg">
          {options.map((o) => (
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
        </div>
      )}
    </div>
  );
}
