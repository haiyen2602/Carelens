"use client";

import { useState } from "react";
import { Clock, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MedicineCombobox } from "@/components/medicine-combobox";
import { useProto } from "@/lib/proto-store";

const defaultTimes: Record<number, string[]> = {
  1: ["08:00"],
  2: ["08:00", "20:00"],
  3: ["08:00", "13:00", "20:00"],
  4: ["07:00", "12:00", "17:00", "21:00"],
};

type MedRow = {
  id: string;
  med: string;
  dose: string;
  perDay: number;
  meal: string;
  times: string[];
};

function newMedRow(): MedRow {
  return {
    id: crypto.randomUUID(),
    med: "",
    dose: "1 viên",
    perDay: 1,
    meal: "Sau ăn",
    times: defaultTimes[1] ?? ["08:00"],
  };
}

export default function PrescribePage() {
  const { patients, createPrescription } = useProto();
  const [patient, setPatient] = useState(patients[0]?.name ?? "");
  const [note, setNote] = useState("Theo dõi huyết áp mỗi sáng");
  const [meds, setMeds] = useState<MedRow[]>([
    {
      id: crypto.randomUUID(),
      med: "Amlodipine 5mg",
      dose: "1 viên",
      perDay: 2,
      meal: "Sau ăn",
      times: defaultTimes[2] ?? ["08:00"],
    },
  ]);

  const updateMed = (id: string, patch: Partial<MedRow>) => {
    setMeds((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  };

  const updatePerDay = (id: string, perDay: number) => {
    updateMed(id, { perDay, times: defaultTimes[perDay] ?? ["08:00"] });
  };

  const updateTime = (id: string, index: number, value: string) => {
    setMeds((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, times: m.times.map((t, i) => (i === index ? value : t)) } : m,
      ),
    );
  };

  const removeMed = (id: string) => {
    setMeds((prev) => (prev.length > 1 ? prev.filter((m) => m.id !== id) : prev));
  };

  const canSubmit = meds.every((m) => m.med.trim().length > 0);

  const submit = () => {
    for (const m of meds) {
      createPrescription({
        patient,
        med: m.med,
        dose: m.dose,
        perDay: m.perDay,
        meal: m.meal,
        note,
        times: m.times,
      });
    }
    toast.success(
      meds.length > 1
        ? `Đã gửi ${meds.length} thuốc vào hàng đợi duyệt HITL`
        : "Đã gửi phác đồ vào hàng đợi duyệt HITL",
    );
    setMeds([newMedRow()]);
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Kê đơn thuốc</h1>
        <p className="text-sm text-muted-foreground">
          Hệ thống sinh thời khóa biểu, bác sĩ xác nhận trước khi thông báo tới bệnh nhân.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        <section className="surface-card space-y-5 p-5">
          <div className="space-y-2">
            <Label>Bệnh nhân</Label>
            <Select value={patient} onValueChange={setPatient}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {patients.map((p) => (
                  <SelectItem key={p.id} value={p.name}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-4">
            {meds.map((m, i) => (
              <div key={m.id} className="space-y-4 rounded-xl border border-border p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-muted-foreground">Thuốc {i + 1}</p>
                  {meds.length > 1 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive"
                      onClick={() => removeMed(m.id)}
                    >
                      <Trash2 className="mr-1 h-4 w-4" /> Xóa
                    </Button>
                  )}
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor={`med-${m.id}`}>Tên thuốc</Label>
                    <MedicineCombobox
                      id={`med-${m.id}`}
                      value={m.med}
                      onChange={(v) => updateMed(m.id, { med: v })}
                      onSelectDrug={(d) => updateMed(m.id, { med: d.name, dose: d.defaultDose })}
                      placeholder="Gõ để tìm thuốc, vd. Amlodipine..."
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`dose-${m.id}`}>Liều dùng</Label>
                    <Input
                      id={`dose-${m.id}`}
                      value={m.dose}
                      onChange={(e) => updateMed(m.id, { dose: e.target.value })}
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
                    <Select value={m.meal} onValueChange={(v) => updateMed(m.id, { meal: v })}>
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
                  <p className="text-xs text-muted-foreground">
                    Giờ mặc định theo số lần/ngày — chỉnh lại nếu bệnh nhân có lịch sinh hoạt khác.
                  </p>
                </div>
              </div>
            ))}
          </div>

          <Button
            variant="outline"
            className="w-full"
            onClick={() => setMeds((prev) => [...prev, newMedRow()])}
          >
            <Plus className="mr-1 h-4 w-4" /> Thêm thuốc
          </Button>

          <div className="space-y-2">
            <Label htmlFor="note">Lưu ý</Label>
            <Textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </div>

          <Button className="w-full" size="lg" disabled={!canSubmit} onClick={submit}>
            <Plus className="mr-1 h-4 w-4" /> Chốt phác đồ & gửi duyệt
          </Button>
        </section>

        <section className="surface-card space-y-5 p-5">
          <div>
            <h2 className="flex items-center gap-2 font-bold">
              <Clock className="h-4 w-4 text-primary" /> Preview timeline 1 ngày
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Safeband ±30 phút quanh mỗi mốc giờ.
            </p>
          </div>

          {meds.map((m) => {
            const times = m.times;
            return (
              <div key={m.id}>
                <p className="truncate text-sm font-semibold text-primary">
                  {m.med || "(chưa đặt tên thuốc)"}
                </p>
                <ol className="mt-2 space-y-3">
                  {times.map((t) => (
                    <li key={t} className="flex gap-3">
                      <span className="w-14 shrink-0 font-mono text-sm font-semibold">{t}</span>
                      <div className="min-w-0 flex-1 rounded-lg border border-border p-3">
                        <p className="truncate font-semibold">{m.med || "(chưa đặt tên thuốc)"}</p>
                        <p className="text-sm text-muted-foreground">
                          {m.dose} · {m.meal}
                        </p>
                        <p className="mt-1 text-xs text-primary">
                          Khung an toàn: {shift(t, -30)} – {shift(t, 30)}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            );
          })}

          <div className="rounded-lg bg-accent p-4 text-sm text-accent-foreground">
            Sau khi bác sĩ duyệt: ghi audit log → kích hoạt phác đồ → thông báo bệnh nhân và người
            thân.
          </div>
        </section>
      </div>
    </div>
  );
}

function shift(hhmm: string, minutes: number) {
  const [h, m] = hhmm.split(":").map(Number);
  const total = ((h ?? 0) * 60 + (m ?? 0) + minutes + 1440) % 1440;
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
