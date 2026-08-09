"use client";

import { useRef, useState } from "react";
import { Check, Pill } from "lucide-react";
import { Input } from "@/components/ui/input";
import { DRUG_DATABASE, type Drug } from "@/lib/drugs";

export function MedicineCombobox({
  id,
  value,
  onChange,
  onSelectDrug,
  placeholder,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  onSelectDrug: (drug: Drug) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const query = value.trim().toLowerCase();
  const matches = query
    ? DRUG_DATABASE.filter((d) => d.name.toLowerCase().includes(query)).slice(0, 6)
    : [];
  const isExactMatch = DRUG_DATABASE.some((d) => d.name.toLowerCase() === query);

  return (
    <div className="relative">
      <Input
        id={id}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          closeTimer.current = setTimeout(() => setOpen(false), 120);
        }}
        placeholder={placeholder}
        autoComplete="off"
        className={isExactMatch ? "border-success pr-8" : undefined}
      />
      {isExactMatch && (
        <Check className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-success" />
      )}

      {open && matches.length > 0 && (
        <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-border bg-card py-1 shadow-lg">
          {matches.map((d) => (
            <button
              key={d.id}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                clearTimeout(closeTimer.current);
                onSelectDrug(d);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-muted"
            >
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-accent text-accent-foreground">
                <Pill className="h-3.5 w-3.5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{d.name}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {d.category} · liều thường dùng {d.defaultDose}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
