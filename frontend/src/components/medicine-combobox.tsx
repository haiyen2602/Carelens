"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Pill } from "lucide-react";
import { Input } from "@/components/ui/input";
import { moTaThuoc, searchDrugs, type Drug } from "@/lib/drugs";

// Cho go xong roi moi goi API. Khong co no thi go "amlodipin" la 9 lan goi
// mang lien tiep, va ket qua ve khong dung thu tu se lam o goi y nhay lung tung.
const CHO_GO_XONG_MS = 250;

export function MedicineCombobox({
  id,
  value,
  onChange,
  onSelectDrug,
  placeholder,
  invalid = false,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  onSelectDrug: (drug: Drug) => void;
  placeholder?: string;
  // Co chu nhung CHUA chon tu danh muc. FB-14: cai nay chan gui don, nen phai
  // thay ngay o o nhap chu khong doi den luc bam nut moi bao.
  invalid?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [matches, setMatches] = useState<Drug[]>([]);
  const [dangTai, setDangTai] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const query = value.trim();

  useEffect(() => {
    if (!query) {
      setMatches([]);
      setLoi(null);
      return;
    }

    // Huy request cu khi nguoi dung go tiep: cau tra loi cho tu khoa da cu
    // khong duoc ghi de len ket qua moi.
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setDangTai(true);
      try {
        setMatches(await searchDrugs(query, controller.signal));
        setLoi(null);
      } catch (err) {
        if (controller.signal.aborted) return; // bi huy, khong phai loi
        setMatches([]);
        setLoi(err instanceof Error ? err.message : "Không tra cứu được thuốc");
      } finally {
        if (!controller.signal.aborted) setDangTai(false);
      }
    }, CHO_GO_XONG_MS);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  // So voi ten day du trong danh muc, khong phai voi chu bac si go do.
  const isExactMatch = matches.some((d) => d.tenThuoc.toLowerCase() === query.toLowerCase());
  const hienGoiY = open && Boolean(query) && (matches.length > 0 || dangTai || Boolean(loi));

  const openNow = () => {
    clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const scheduleClose = () => {
    closeTimer.current = setTimeout(() => setOpen(false), 150);
  };

  return (
    <div className="relative" onMouseEnter={openNow} onMouseLeave={scheduleClose}>
      <Input
        id={id}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          openNow();
        }}
        onFocus={openNow}
        onBlur={scheduleClose}
        placeholder={placeholder}
        autoComplete="off"
        aria-busy={dangTai}
        aria-invalid={invalid || undefined}
        className={
          isExactMatch ? "border-success pr-8" : invalid ? "border-destructive" : undefined
        }
      />
      {isExactMatch && (
        <Check className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-success" />
      )}

      {hienGoiY && (
        <div
          role="listbox"
          className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-border bg-card py-1 shadow-lg"
        >
          {loi && <p className="px-3 py-2 text-sm text-destructive">{loi}</p>}

          {/* Chi bao "dang tim" khi CHUA co gi de hien - go tiep ma danh sach
              cu bien mat roi hien chu "dang tim" lam man hinh nhap nhay. */}
          {dangTai && matches.length === 0 && !loi && (
            <p className="px-3 py-2 text-sm text-muted-foreground">Đang tìm…</p>
          )}

          {matches.map((d) => (
            <button
              key={d.drugId}
              type="button"
              role="option"
              aria-selected={d.tenThuoc.toLowerCase() === query.toLowerCase()}
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
                <span className="block truncate font-medium">{d.tenThuoc}</span>
                <span className="block truncate text-xs text-muted-foreground">{moTaThuoc(d)}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
