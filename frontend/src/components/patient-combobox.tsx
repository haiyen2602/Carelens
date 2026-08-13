"use client";

import { useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { Input } from "@/components/ui/input";

export type PatientOption = {
  id: string;
  name: string;
  displayId: string;
};

export function PatientCombobox({
  id,
  options,
  value,
  onChange,
  placeholder,
}: {
  id?: string;
  options: PatientOption[];
  value: string;
  onChange: (id: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const selected = options.find((p) => p.id === value);
  const q = query.trim().toLowerCase();
  const matches = q
    ? options.filter(
        (p) => p.name.toLowerCase().includes(q) || p.displayId.toLowerCase().includes(q),
      )
    : options;

  const openNow = () => {
    clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const scheduleClose = () => {
    closeTimer.current = setTimeout(() => setOpen(false), 150);
  };

  return (
    <div className="relative" onMouseEnter={openNow} onMouseLeave={scheduleClose}>
      <div className="relative">
        <Input
          id={id}
          value={open ? query : (selected?.name ?? "")}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            setQuery("");
            openNow();
          }}
          onBlur={scheduleClose}
          placeholder={placeholder ?? "Tìm theo tên hoặc ID bệnh nhân..."}
          autoComplete="off"
          className="pr-8"
        />
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      </div>

      {open && (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-border bg-card py-1 shadow-lg">
          {matches.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted-foreground">Không tìm thấy bệnh nhân.</p>
          )}
          {matches.map((p) => {
            const isSelected = p.id === value;
            return (
              <button
                key={p.id}
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  clearTimeout(closeTimer.current);
                  onChange(p.id);
                  setQuery("");
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between gap-2.5 px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{p.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    ID: {p.displayId}
                  </span>
                </span>
                {isSelected && <Check className="h-4 w-4 shrink-0 text-primary" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
