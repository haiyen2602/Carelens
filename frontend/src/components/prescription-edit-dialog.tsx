"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MedicineCombobox } from "@/components/medicine-combobox";
import { DEFAULT_TIMES } from "@/lib/dose-schedule";
import type { Prescription } from "@/lib/proto-store";

type EditableMed = {
  id: string;
  med: string;
  dose: string;
  perDay: number;
  meal: string;
  times: string[];
  startDate: string;
  endDate: string;
  hasCycle: boolean;
  cycleOnDays: number;
  cycleOffDays: number;
};

function toEditable(p: Prescription): EditableMed {
  return {
    id: p.id,
    med: p.med,
    dose: p.dose,
    perDay: p.perDay,
    meal: p.meal,
    times: p.times,
    startDate: p.startDate,
    endDate: p.endDate,
    hasCycle: p.cycle !== null,
    cycleOnDays: p.cycle?.onDays ?? 5,
    cycleOffDays: p.cycle?.offDays ?? 2,
  };
}

export function PrescriptionEditDialog({
  open,
  onOpenChange,
  meds,
  patient,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  meds: Prescription[];
  patient: string;
  onSave: (rows: EditableMed[]) => void;
}) {
  const [rows, setRows] = useState<EditableMed[]>([]);

  useEffect(() => {
    if (open) setRows(meds.map(toEditable));
  }, [open, meds]);

  const updateRow = (id: string, patch: Partial<EditableMed>) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const updatePerDay = (id: string, perDay: number) => {
    updateRow(id, { perDay, times: DEFAULT_TIMES[perDay] ?? ["08:00"] });
  };

  const updateTime = (id: string, index: number, value: string) => {
    setRows((prev) =>
      prev.map((r) =>
        r.id === id ? { ...r, times: r.times.map((t, i) => (i === index ? value : t)) } : r,
      ),
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Điều chỉnh thủ công — {patient}</DialogTitle>
          <DialogDescription>
            Chỉnh từng thuốc như khi kê đơn. Thay đổi sẽ được ghi vào audit log khi lưu.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {rows.map((m, i) => (
            <div key={m.id} className="space-y-4 rounded-xl border border-border p-4">
              <p className="text-sm font-semibold text-muted-foreground">Thuốc {i + 1}</p>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor={`edit-med-${m.id}`}>Tên thuốc</Label>
                  <MedicineCombobox
                    id={`edit-med-${m.id}`}
                    value={m.med}
                    onChange={(v) => updateRow(m.id, { med: v })}
                    onSelectDrug={(d) => updateRow(m.id, { med: d.name, dose: d.defaultDose })}
                    placeholder="Gõ để tìm thuốc, vd. Amlodipine..."
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`edit-dose-${m.id}`}>Liều dùng</Label>
                  <Input
                    id={`edit-dose-${m.id}`}
                    value={m.dose}
                    onChange={(e) => updateRow(m.id, { dose: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Số lần/ngày</Label>
                  <Select
                    value={String(m.perDay)}
                    onValueChange={(v) => updatePerDay(m.id, Number(v))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[1, 2, 3, 4].map((n) => (
                        <SelectItem key={n} value={String(n)}>
                          {n} lần/ngày
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Bữa ăn</Label>
                  <Select value={m.meal} onValueChange={(v) => updateRow(m.id, { meal: v })}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {["Trước ăn", "Sau ăn", "Không phụ thuộc bữa ăn", "Trước khi ngủ"].map(
                        (mm) => (
                          <SelectItem key={mm} value={mm}>
                            {mm}
                          </SelectItem>
                        ),
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Giờ uống</Label>
                <div className="flex flex-wrap gap-2">
                  {m.times.map((t, idx) => (
                    <Input
                      key={idx}
                      type="time"
                      value={t}
                      onChange={(e) => updateTime(m.id, idx, e.target.value)}
                      className="w-32"
                    />
                  ))}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor={`edit-start-${m.id}`}>Ngày bắt đầu</Label>
                  <Input
                    id={`edit-start-${m.id}`}
                    type="date"
                    value={m.startDate}
                    onChange={(e) => updateRow(m.id, { startDate: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`edit-end-${m.id}`}>Ngày kết thúc (nếu có)</Label>
                  <Input
                    id={`edit-end-${m.id}`}
                    type="date"
                    value={m.endDate}
                    min={m.startDate}
                    onChange={(e) => updateRow(m.id, { endDate: e.target.value })}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <input
                    id={`edit-cycle-${m.id}`}
                    type="checkbox"
                    className="h-4 w-4 rounded border-input"
                    checked={m.hasCycle}
                    onChange={(e) => updateRow(m.id, { hasCycle: e.target.checked })}
                  />
                  <Label htmlFor={`edit-cycle-${m.id}`} className="cursor-pointer">
                    Uống theo chu kỳ (đợt uống — đợt nghỉ)
                  </Label>
                </div>
                {m.hasCycle && (
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-muted-foreground">Uống</span>
                    <Input
                      type="number"
                      min={1}
                      value={m.cycleOnDays}
                      onChange={(e) =>
                        updateRow(m.id, { cycleOnDays: Number(e.target.value) || 1 })
                      }
                      className="w-20"
                    />
                    <span className="text-muted-foreground">ngày, nghỉ</span>
                    <Input
                      type="number"
                      min={0}
                      value={m.cycleOffDays}
                      onChange={(e) =>
                        updateRow(m.id, { cycleOffDays: Number(e.target.value) || 0 })
                      }
                      className="w-20"
                    />
                    <span className="text-muted-foreground">ngày, lặp lại</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Hủy
          </Button>
          <Button
            onClick={() => {
              onSave(rows);
              onOpenChange(false);
            }}
          >
            Lưu thay đổi
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
