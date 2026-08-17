"use client";

import { useEffect, useState } from "react";
import { Clock, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { HoverSelect } from "@/components/hover-select";
import { MedicineCombobox } from "@/components/medicine-combobox";
import { useAuth } from "@/lib/auth";
import { goiYLieu } from "@/lib/drugs";
import { listPatients, type PatientRecord } from "@/lib/patients";
import { PatientCombobox } from "@/components/patient-combobox";
import { DoseMiniCalendar } from "@/components/dose-mini-calendar";
import { useProto } from "@/lib/proto-store";
import { DEFAULT_TIMES, appliesOnDate, shiftTime, today } from "@/lib/dose-schedule";

const MEAL_OPTIONS = ["Trước ăn", "Sau ăn", "Không phụ thuộc bữa ăn", "Trước khi ngủ"];

// Bac si go so vien bang chu tu do ("2 vien", "1 goi"), nhung phan doi chieu
// anh (backend/services/photo_verification/matcher.py, che do EXACT) can mot
// con so nguyen. Doc tam so dau tien trong chuoi - khong doan duoc thi de
// trong, lieu do se roi ve nut bam xac nhan thay vi anh (van hop le, chi la
// bang chung yeu hon).
function docSoVien(dose: string): number | null {
  const khop = dose.match(/\d+/);
  return khop ? Number(khop[0]) : null;
}

// So ngay dung THUOC NAY, tinh tu startDate den endDate (ca 2 dau bao gom).
// endDate rong -> tra null, backend tu dung mac dinh (SO_NGAY_MAC_DINH).
function tinhSoNgayDung(startDate: string, endDate: string): number | null {
  if (!endDate) return null;
  const soNgay =
    Math.round(
      (new Date(`${endDate}T00:00:00Z`).getTime() - new Date(`${startDate}T00:00:00Z`).getTime()) /
        86_400_000,
    ) + 1;
  return soNgay > 0 ? soNgay : null;
}

const defaultTimes = DEFAULT_TIMES;

type MedRow = {
  id: string;
  med: string;
  // Danh tinh that trong danh muc thuoc. Rong khi bac si tu go mot ten khong
  // co trong danh muc — van ke don duoc, nhung lieu do se khong xac minh duoc
  // bang anh (khong biet dang bao che), phai xac nhan bang nut bam.
  drugId: string;
  dangThuoc: string;
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

function newMedRow(startDate?: string, endDate?: string): MedRow {
  return {
    id: crypto.randomUUID(),
    med: "",
    drugId: "",
    dangThuoc: "",
    dose: "1 viên",
    perDay: 1,
    meal: "Sau ăn",
    times: defaultTimes[1] ?? ["08:00"],
    startDate: startDate ?? today(),
    endDate: endDate ?? "",
    hasCycle: false,
    cycleOnDays: 5,
    cycleOffDays: 2,
  };
}

export default function PrescribePage() {
  const { createPrescription, pushActivity } = useProto();
  const { accessToken } = useAuth();
  // Danh sach benh nhan THAT (bang `patient`), khac han mang `patients` mock
  // cua useProto() - mang do phuc vu dashboard tuan thu (age/condition/
  // adherence), chua co ben backend. Xem lib/patients.ts.
  const [benhNhanThat, setBenhNhanThat] = useState<PatientRecord[]>([]);
  const [patientId, setPatientId] = useState("");
  const [note, setNote] = useState("");
  const [dangGui, setDangGui] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  // Bat dau bang mot dong trong. Truoc day dien san "Amlodipine 5mg" - mot
  // thuoc trong danh sach mock, khong ton tai trong danh muc that, nen de lai
  // se thanh don thuoc khong tra cuu duoc dang bao che.
  const [meds, setMeds] = useState<MedRow[]>([newMedRow()]);

  useEffect(() => {
    listPatients(undefined, accessToken)
      .then((ds) => {
        setBenhNhanThat(ds);
        setPatientId((hienTai) => hienTai || (ds[0]?.id ?? ""));
      })
      .catch((err) => {
        console.error("Không tải được danh sách bệnh nhân:", err);
        toast.error("Không tải được danh sách bệnh nhân");
      });
  }, [accessToken]);

  const patientOptions = benhNhanThat.map((p, i) => ({
    id: p.id,
    name: p.fullName,
    displayId: `BN${String(i + 1).padStart(4, "0")}`,
  }));

  const updateMed = (id: string, patch: Partial<MedRow>) => {
    setMeds((prev) => {
      const isFirst = prev[0]?.id === id;
      const syncDates: Partial<Pick<MedRow, "startDate" | "endDate">> = {};
      if (isFirst && "startDate" in patch) syncDates.startDate = patch.startDate;
      if (isFirst && "endDate" in patch) syncDates.endDate = patch.endDate;
      const hasSync = Object.keys(syncDates).length > 0;
      return prev.map((m, i) => {
        if (m.id === id) return { ...m, ...patch };
        if (hasSync && i > 0) return { ...m, ...syncDates };
        return m;
      });
    });
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

  const canSubmit = Boolean(patientId) && meds.every((m) => m.med.trim().length > 0) && !dangGui;

  const activeMeds = meds.filter((m) => m.med.trim().length > 0);
  const timeline = [
    ...meds
      .reduce((map, m) => {
        for (const t of m.times) {
          const list = map.get(t) ?? [];
          list.push(m);
          map.set(t, list);
        }
        return map;
      }, new Map<string, MedRow[]>())
      .entries(),
  ].sort((a, b) => a[0].localeCompare(b[0]));

  const submit = async () => {
    setDangGui(true);
    try {
      // MOT lan goi cho ca don, khong phai tung thuoc mot: hai thuoc cung gio
      // phai nam chung mot phac do de backend gop dung 1 dose_event thay vi 2
      // (backend/services/scheduling/generator.py - benh nhan bay ca nam
      // thuoc ra roi chup MOT anh, khong phai chup tung thuoc).
      await createPrescription({
        patientId,
        note,
        items: meds.map((m) => ({
          drugId: m.drugId || null,
          tenThuoc: m.med,
          dangThuoc: m.dangThuoc || null,
          duongDung: null, // backend tu tra lai tu drugId neu co, xem service.py::_chuan_hoa_item
          hamLuong: null,
          lieuDung: m.dose,
          thoiDiemDung: m.meal,
          soVienMoiLan: docSoVien(m.dose),
          gioNhac: m.times,
          dosesPerDay: m.perDay,
          hasCycle: m.hasCycle,
          cycleOnDays: m.hasCycle ? m.cycleOnDays : null,
          cycleOffDays: m.hasCycle ? m.cycleOffDays : null,
          startDate: m.startDate,
          durationDays: tinhSoNgayDung(m.startDate, m.endDate),
        })),
      });
      toast.success(
        meds.length > 1
          ? `Đã duyệt và kích hoạt phác đồ (${meds.length} thuốc)`
          : "Đã duyệt và kích hoạt phác đồ",
      );
      pushActivity(
        "Đã xử lý xong bệnh nhân",
        `Kích hoạt phác đồ (${meds.length} thuốc) cho ${selectedPatientName || "bệnh nhân"}.`,
      );
      setMeds([newMedRow()]);
      setNote("");
      setConfirmOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tạo được đơn thuốc");
    } finally {
      setDangGui(false);
    }
  };

  const selectedPatientName = patientOptions.find((p) => p.id === patientId)?.name ?? "";

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
            <Label htmlFor="patient">Bệnh nhân</Label>
            <PatientCombobox
              id="patient"
              options={patientOptions}
              value={patientId}
              onChange={setPatientId}
              placeholder={benhNhanThat.length === 0 ? "Đang tải…" : undefined}
            />
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
                      onSelectDrug={(d) =>
                        updateMed(m.id, {
                          med: d.tenThuoc,
                          drugId: d.drugId,
                          dangThuoc: d.dangThuoc,
                          dose: goiYLieu(d),
                        })
                      }
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
                    <HoverSelect
                      value={String(m.perDay)}
                      onChange={(v) => updatePerDay(m.id, Number(v))}
                      options={[1, 2, 3, 4].map((n) => ({
                        value: String(n),
                        label: `${n} lần/ngày`,
                      }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Bữa ăn</Label>
                    <HoverSelect
                      value={m.meal}
                      onChange={(v) => updateMed(m.id, { meal: v })}
                      options={MEAL_OPTIONS.map((mm) => ({ value: mm, label: mm }))}
                    />
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

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor={`start-${m.id}`}>Ngày bắt đầu</Label>
                    <Input
                      id={`start-${m.id}`}
                      type="date"
                      value={m.startDate}
                      onChange={(e) => updateMed(m.id, { startDate: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`end-${m.id}`}>Ngày kết thúc (nếu có)</Label>
                    <Input
                      id={`end-${m.id}`}
                      type="date"
                      value={m.endDate}
                      min={m.startDate}
                      onChange={(e) => updateMed(m.id, { endDate: e.target.value })}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      id={`cycle-${m.id}`}
                      type="checkbox"
                      className="h-4 w-4 rounded border-input"
                      checked={m.hasCycle}
                      onChange={(e) => updateMed(m.id, { hasCycle: e.target.checked })}
                    />
                    <Label htmlFor={`cycle-${m.id}`} className="cursor-pointer">
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
                          updateMed(m.id, { cycleOnDays: Number(e.target.value) || 1 })
                        }
                        className="w-20"
                      />
                      <span className="text-muted-foreground">ngày, nghỉ</span>
                      <Input
                        type="number"
                        min={0}
                        value={m.cycleOffDays}
                        onChange={(e) =>
                          updateMed(m.id, { cycleOffDays: Number(e.target.value) || 0 })
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

          <Button
            variant="outline"
            className="w-full"
            onClick={() =>
              setMeds((prev) => [...prev, newMedRow(prev[0]?.startDate, prev[0]?.endDate)])
            }
          >
            <Plus className="mr-1 h-4 w-4" /> Thêm thuốc
          </Button>

          <div className="space-y-2">
            <Label htmlFor="note">Lưu ý</Label>
            <Textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </div>

          <Button
            className="w-full"
            size="lg"
            disabled={!canSubmit}
            onClick={() => setConfirmOpen(true)}
          >
            <Plus className="mr-1 h-4 w-4" /> Chốt phác đồ & gửi duyệt
          </Button>
        </section>

        <section className="surface-card space-y-5 p-5">
          <div>
            <h2 className="flex items-center gap-2 font-bold">
              <Clock className="h-4 w-4 text-primary" /> Preview timeline 1 ngày
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Safeband ±30 phút quanh mỗi mốc giờ. Mỗi khung giờ gộp tất cả thuốc cần uống cùng
              lúc.
            </p>
          </div>

          <ol className="space-y-3">
            {timeline.map(([t, ms]) => (
              <li key={t} className="flex gap-3">
                <span className="w-14 shrink-0 font-mono text-sm font-semibold">{t}</span>
                <div className="min-w-0 flex-1 space-y-2">
                  {ms.map((m) => (
                    <div key={m.id} className="rounded-lg border border-border p-3">
                      <p className="truncate font-semibold">
                        {m.med || "(chưa đặt tên thuốc)"}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {m.dose} · {m.meal}
                      </p>
                    </div>
                  ))}
                  <p className="text-xs text-primary">
                    Khung an toàn: {shiftTime(t, -30)} – {shiftTime(t, 30)}
                  </p>
                </div>
              </li>
            ))}
            {timeline.length === 0 && (
              <p className="text-sm text-muted-foreground">Chưa có giờ uống nào được đặt.</p>
            )}
          </ol>

          <div>
            <h2 className="font-bold">Lịch uống thuốc</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Chấm xanh đánh dấu ngày bệnh nhân cần uống thuốc.
            </p>
            <div className="mt-3">
              <DoseMiniCalendar
                initialDate={activeMeds[0]?.startDate}
                isDoseDay={(iso) => activeMeds.some((m) => appliesOnDate(m, iso))}
              />
            </div>
          </div>

          <div className="rounded-lg bg-accent p-4 text-sm text-accent-foreground">
            Sau khi bác sĩ duyệt: ghi audit log → kích hoạt phác đồ → thông báo bệnh nhân và người
            thân.
          </div>
        </section>
      </div>

      <Dialog open={confirmOpen} onOpenChange={(open) => !dangGui && setConfirmOpen(open)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Xác nhận duyệt phác đồ</DialogTitle>
            <DialogDescription>
              Bấm "Duyệt & kích hoạt" để chốt phác đồ này ngay — hệ thống sẽ ghi audit log, kích
              hoạt lịch nhắc và thông báo tới bệnh nhân/người thân. Thao tác này thay cho bước
              duyệt riêng ở hàng đợi.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 rounded-lg border border-border p-4 text-sm">
            <p>
              <span className="text-muted-foreground">Bệnh nhân: </span>
              <span className="font-semibold">{selectedPatientName || "(chưa chọn)"}</span>
            </p>
            <ul className="space-y-1.5">
              {activeMeds.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate font-medium">{m.med}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {m.dose} · {m.times.join(", ")}
                  </span>
                </li>
              ))}
            </ul>
            {note && <p className="text-muted-foreground">Lưu ý: {note}</p>}
          </div>

          <DialogFooter>
            <Button variant="outline" disabled={dangGui} onClick={() => setConfirmOpen(false)}>
              Huỷ
            </Button>
            <Button disabled={dangGui} onClick={submit}>
              {dangGui ? "Đang duyệt…" : "Duyệt & kích hoạt"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
