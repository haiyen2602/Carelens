"use client";

import { Eye, Pencil, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import { HoverSelect } from "@/components/hover-select";
import { MedicineCombobox } from "@/components/medicine-combobox";
import {
  CAN_NANG_KG,
  CHIEU_CAO_CM,
  kiemTraCanNang,
  kiemTraChieuCao,
} from "@/lib/body-metrics";
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
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";
import { DEFAULT_TIMES, today } from "@/lib/dose-schedule";
import { goiYLieu } from "@/lib/drugs";
import { listEscalations, type Escalation } from "@/lib/escalations";
import {
  listPrescriptions,
  updatePrescription,
  type PrescriptionRecord,
} from "@/lib/prescriptions";
import { useProto } from "@/lib/proto-store";
import {
  listReportingPatients,
  setPatientWatch,
  updatePatientHealth,
  type PatientHealthPatch,
  type ReportingPatient,
} from "@/lib/reporting";

const DEBOUNCE_MS = 300;

const MEAL_OPTIONS = ["Trước ăn", "Sau ăn", "Không phụ thuộc bữa ăn", "Trước khi ngủ"];

const GENDER_LABEL: Record<string, string> = {
  nam: "Nam",
  nu: "Nữ",
  khac: "Khác",
};

const SEVERITY_TONE: Record<string, string> = {
  LOW: "bg-secondary text-secondary-foreground",
  MEDIUM: "bg-warning/25 text-warning-foreground",
  HIGH: "bg-destructive/12 text-destructive",
};

function tinhTuoi(yearOfBirth: number | null): number | null {
  return yearOfBirth ? new Date().getFullYear() - yearOfBirth : null;
}

const DETAIL_TABS = [
  { key: "health", label: "Tình trạng sức khỏe" },
  { key: "prescriptions", label: "Phác đồ" },
  { key: "adherence", label: "Tuân thủ" },
] as const;
type DetailTab = (typeof DETAIL_TABS)[number]["key"];

function HealthTab({
  patient,
  onSaved,
}: {
  patient: ReportingPatient;
  onSaved: (patch: PatientHealthPatch) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [gender, setGender] = useState(patient.gender ?? "");
  const [heightCm, setHeightCm] = useState(patient.heightCm?.toString() ?? "");
  const [weightKg, setWeightKg] = useState(patient.weightKg?.toString() ?? "");
  const [note, setNote] = useState(patient.note ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setGender(patient.gender ?? "");
    setHeightCm(patient.heightCm?.toString() ?? "");
    setWeightKg(patient.weightKg?.toString() ?? "");
    setNote(patient.note ?? "");
    setEditing(false);
  }, [patient.id, patient.gender, patient.heightCm, patient.weightKg, patient.note]);

  const age = tinhTuoi(patient.yearOfBirth);
  const { pushActivity } = useProto();
  const { accessToken } = useAuth();
  const chieuCao = kiemTraChieuCao(heightCm);
  const canNang = kiemTraCanNang(weightKg);

  const save = async () => {
    // Chan truoc khi goi mang - loi 422 tu backend khong noi ro o nao sai.
    if (chieuCao.loi || canNang.loi) {
      toast.error(chieuCao.loi ?? canNang.loi ?? "");
      return;
    }
    setSaving(true);
    try {
      const patch = await updatePatientHealth(
        patient.id,
        {
          gender: gender || undefined,
          heightCm: heightCm ? Number(heightCm) : undefined,
          weightKg: weightKg ? Number(weightKg) : undefined,
          note: note || undefined,
        },
        accessToken,
      );
      onSaved(patch);
      pushActivity("Đã xử lý xong bệnh nhân", `Cập nhật hồ sơ sức khỏe của ${patient.fullName}.`);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <div className="space-y-4">
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted-foreground">Tuổi</dt>
            <dd className="font-semibold">{age ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Giới tính</dt>
            <dd className="font-semibold">
              {patient.gender ? (GENDER_LABEL[patient.gender] ?? patient.gender) : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Chiều cao</dt>
            <dd className="font-semibold">{patient.heightCm ? `${patient.heightCm} cm` : "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Cân nặng</dt>
            <dd className="font-semibold">{patient.weightKg ? `${patient.weightKg} kg` : "—"}</dd>
          </div>
        </dl>
        <div>
          <p className="text-xs text-muted-foreground">Bệnh nền / chẩn đoán</p>
          <p className="mt-1 text-sm">{patient.note || "Chưa có ghi chú."}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
          Chỉnh sửa
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor={`gender-${patient.id}`}>Giới tính</Label>
          <select
            id={`gender-${patient.id}`}
            value={gender}
            onChange={(e) => setGender(e.target.value)}
            className="h-10 w-full rounded-xl border border-input bg-card px-3 text-sm outline-none focus:border-primary"
          >
            <option value="">Chưa rõ</option>
            <option value="nam">Nam</option>
            <option value="nu">Nữ</option>
            <option value="khac">Khác</option>
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor={`height-${patient.id}`}>Chiều cao (cm)</Label>
          <Input
            id={`height-${patient.id}`}
            type="number"
            min={CHIEU_CAO_CM.min}
            max={CHIEU_CAO_CM.max}
            aria-invalid={chieuCao.loi !== null || undefined}
            value={heightCm}
            onChange={(e) => setHeightCm(e.target.value)}
          />
          {chieuCao.loi && <p className="text-sm text-destructive">{chieuCao.loi}</p>}
          {chieuCao.canhBao && <p className="text-sm text-muted-foreground">{chieuCao.canhBao}</p>}
        </div>
        <div className="space-y-2">
          <Label htmlFor={`weight-${patient.id}`}>Cân nặng (kg)</Label>
          <Input
            id={`weight-${patient.id}`}
            type="number"
            min={CAN_NANG_KG.min}
            max={CAN_NANG_KG.max}
            aria-invalid={canNang.loi !== null || undefined}
            value={weightKg}
            onChange={(e) => setWeightKg(e.target.value)}
          />
          {canNang.loi && <p className="text-sm text-destructive">{canNang.loi}</p>}
          {canNang.canhBao && <p className="text-sm text-muted-foreground">{canNang.canhBao}</p>}
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor={`note-${patient.id}`}>Bệnh nền / chẩn đoán</Label>
        <Textarea
          id={`note-${patient.id}`}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
        />
      </div>
      <div className="flex gap-2">
        <Button size="sm" disabled={saving} onClick={save}>
          {saving ? "Đang lưu…" : "Lưu"}
        </Button>
        <Button variant="outline" size="sm" disabled={saving} onClick={() => setEditing(false)}>
          Huỷ
        </Button>
      </div>
    </div>
  );
}

// So ngay dung THUOC NAY, tinh tu startDate den endDate (ca 2 dau bao gom).
// endDate rong -> null, backend tu dung mac dinh.
function tinhSoNgayDung(startDate: string, endDate: string): number | null {
  if (!endDate) return null;
  const soNgay =
    Math.round(
      (new Date(`${endDate}T00:00:00Z`).getTime() - new Date(`${startDate}T00:00:00Z`).getTime()) /
        86_400_000,
    ) + 1;
  return soNgay > 0 ? soNgay : null;
}

// Ngay uong CUOI CUNG (bao gom) tinh tu startDate + so ngay dung.
function tinhNgayKetThuc(startDate: string, durationDays: number): string {
  const d = new Date(`${startDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + Math.max(durationDays - 1, 0));
  return d.toISOString().slice(0, 10);
}

// Bac si go so vien bang chu tu do - phan doi chieu anh can mot con so
// nguyen, doc tam so dau tien trong chuoi (cung logic voi prescribe/page.tsx).
function docSoVien(dose: string): number | null {
  const khop = dose.match(/\d+/);
  return khop ? Number(khop[0]) : null;
}

type EditMedRow = {
  id: string;
  drugId: string;
  med: string;
  dangThuoc: string;
  dose: string;
  perDay: number;
  meal: string;
  times: string[];
  startDate: string;
  endDate: string;
};

function itemToEditRow(
  it: PrescriptionRecord["items"][number],
  presc: PrescriptionRecord,
): EditMedRow {
  const startDate = it.startDate ?? presc.startDate;
  const durationDays = it.durationDays ?? presc.durationDays;
  return {
    id: crypto.randomUUID(),
    drugId: it.drugId,
    med: it.tenThuoc,
    dangThuoc: it.dangThuoc,
    dose: it.lieuDung,
    perDay: it.gioNhac.length || 1,
    meal: "",
    times: it.gioNhac.length ? it.gioNhac : ["08:00"],
    startDate,
    endDate: tinhNgayKetThuc(startDate, durationDays),
  };
}

function newEditRow(): EditMedRow {
  return {
    id: crypto.randomUUID(),
    drugId: "",
    med: "",
    dangThuoc: "",
    dose: "1 viên",
    perDay: 1,
    meal: "Sau ăn",
    times: DEFAULT_TIMES[1] ?? ["08:00"],
    startDate: today(),
    endDate: "",
  };
}

function EditPrescriptionDialog({
  prescription,
  patientName,
  open,
  onOpenChange,
  onSaved,
}: {
  prescription: PrescriptionRecord;
  patientName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (p: PrescriptionRecord) => void;
}) {
  const [meds, setMeds] = useState<EditMedRow[]>([]);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const { pushActivity } = useProto();

  useEffect(() => {
    setMeds(prescription.items.map((it) => itemToEditRow(it, prescription)));
    setNote(prescription.note ?? "");
  }, [prescription]);

  const updateMed = (id: string, patch: Partial<EditMedRow>) => {
    setMeds((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  };
  const updatePerDay = (id: string, perDay: number) => {
    updateMed(id, { perDay, times: DEFAULT_TIMES[perDay] ?? ["08:00"] });
  };
  const updateTime = (id: string, idx: number, value: string) => {
    setMeds((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, times: m.times.map((t, i) => (i === idx ? value : t)) } : m,
      ),
    );
  };
  const removeMed = (id: string) => {
    setMeds((prev) => (prev.length > 1 ? prev.filter((m) => m.id !== id) : prev));
  };

  // FB-14: giong trang ke don - moi dong PHAI chon tu danh muc, khong chi co chu.
  const canSave = meds.every((m) => m.med.trim().length > 0 && Boolean(m.drugId)) && !saving;

  const save = async () => {
    setSaving(true);
    try {
      const updated = await updatePrescription(prescription.id, {
        note,
        items: meds.map((m) => ({
          drugId: m.drugId,
          tenThuoc: m.med,
          dangThuoc: m.dangThuoc || null,
          duongDung: null,
          hamLuong: null,
          lieuDung: m.dose,
          thoiDiemDung: m.meal || null,
          soVienMoiLan: docSoVien(m.dose),
          gioNhac: m.times,
          startDate: m.startDate,
          durationDays: tinhSoNgayDung(m.startDate, m.endDate),
        })),
      });
      onSaved(updated);
      pushActivity("Đã xử lý xong bệnh nhân", `Cập nhật phác đồ điều trị của ${patientName}.`);
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !saving && onOpenChange(v)}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Chỉnh sửa phác đồ</DialogTitle>
          <DialogDescription>
            Cập nhật thuốc, liều dùng và lịch uống. Lưu sẽ áp dụng ngay cho các liều chưa tới hạn,
            liều đã ghi nhận (đã uống/bỏ lỡ) giữ nguyên.
          </DialogDescription>
        </DialogHeader>

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
                  <Label htmlFor={`emed-${m.id}`}>Tên thuốc</Label>
                  <MedicineCombobox
                    id={`emed-${m.id}`}
                    value={m.med}
                    onChange={(v) =>
                      // Go tay = huy lua chon cu, xem MedRow.drugId o prescribe/page.tsx.
                      updateMed(m.id, { med: v, drugId: "", dangThuoc: "" })
                    }
                    onSelectDrug={(d) =>
                      updateMed(m.id, {
                        med: d.tenThuoc,
                        drugId: d.drugId,
                        dangThuoc: d.dangThuoc,
                        dose: goiYLieu(d),
                      })
                    }
                    placeholder="Gõ để tìm thuốc, vd. Amlodipine..."
                    invalid={m.med.trim().length > 0 && !m.drugId}
                  />
                  {m.med.trim().length > 0 && !m.drugId && (
                    <p className="text-sm text-destructive">Chọn thuốc từ danh sách gợi ý.</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`edose-${m.id}`}>Liều dùng</Label>
                  <Input
                    id={`edose-${m.id}`}
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
                      aria-label={`Giờ uống lần ${idx + 1}`}
                      value={t}
                      onChange={(e) => updateTime(m.id, idx, e.target.value)}
                      className="w-32"
                    />
                  ))}
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor={`estart-${m.id}`}>Ngày bắt đầu</Label>
                  <Input
                    id={`estart-${m.id}`}
                    type="date"
                    value={m.startDate}
                    onChange={(e) => updateMed(m.id, { startDate: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor={`eend-${m.id}`}>Ngày kết thúc</Label>
                  <Input
                    id={`eend-${m.id}`}
                    type="date"
                    value={m.endDate}
                    min={m.startDate}
                    onChange={(e) => updateMed(m.id, { endDate: e.target.value })}
                  />
                </div>
              </div>
            </div>
          ))}

          <Button
            variant="outline"
            className="w-full"
            onClick={() => setMeds((prev) => [...prev, newEditRow()])}
          >
            <Plus className="mr-1 h-4 w-4" /> Thêm thuốc
          </Button>

          <div className="space-y-2">
            <Label htmlFor="edit-note">Lưu ý</Label>
            <Textarea
              id="edit-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={saving} onClick={() => onOpenChange(false)}>
            Huỷ
          </Button>
          <Button disabled={!canSave} onClick={save}>
            {saving ? "Đang lưu…" : "Lưu thay đổi"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PrescriptionsTab({ patientId, patientName }: { patientId: string; patientName: string }) {
  const [prescriptions, setPrescriptions] = useState<PrescriptionRecord[]>([]);
  const [dangTai, setDangTai] = useState(false);
  const [editing, setEditing] = useState<PrescriptionRecord | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDangTai(true);
    listPrescriptions({ patientId })
      .then((ps) => {
        if (!cancelled) setPrescriptions(ps);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setDangTai(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  if (dangTai) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (prescriptions.length === 0) {
    return <p className="text-sm text-muted-foreground">Chưa có phác đồ nào.</p>;
  }

  return (
    <div className="space-y-5">
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/60 text-left text-xs font-semibold text-muted-foreground">
              <th className="px-3 py-2">Thuốc</th>
              <th className="px-3 py-2">Liều dùng</th>
              <th className="px-3 py-2">Cữ uống</th>
              <th className="px-3 py-2">Bắt đầu</th>
              <th className="px-3 py-2">Kết thúc</th>
              <th className="px-3 py-2">Lưu ý</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {prescriptions.map((p) =>
              p.items.map((it, idx) => {
                const startDate = it.startDate ?? p.startDate;
                const durationDays = it.durationDays ?? p.durationDays;
                const endDate = tinhNgayKetThuc(startDate, durationDays);
                return (
                  <tr key={`${p.id}-${idx}`} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 font-semibold">{it.tenThuoc}</td>
                    <td className="px-3 py-2 text-muted-foreground">{it.lieuDung}</td>
                    <td className="px-3 py-2 text-muted-foreground">{it.gioNhac.join(", ")}</td>
                    <td className="px-3 py-2 text-muted-foreground">{startDate}</td>
                    <td className="px-3 py-2 text-muted-foreground">{endDate}</td>
                    <td className="px-3 py-2 text-muted-foreground">{p.note || "—"}</td>
                    <td className="px-3 py-2 text-right">
                      <Button variant="outline" size="sm" onClick={() => setEditing(p)}>
                        <Pencil className="mr-1 h-4 w-4" /> Chỉnh sửa
                      </Button>
                    </td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <EditPrescriptionDialog
          prescription={editing}
          patientName={patientName}
          open={!!editing}
          onOpenChange={(v) => !v && setEditing(null)}
          onSaved={(updated) =>
            setPrescriptions((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
          }
        />
      )}
    </div>
  );
}

function AdherenceTab({ patient }: { patient: ReportingPatient }) {
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [dangTai, setDangTai] = useState(false);
  const { accessToken } = useAuth();

  useEffect(() => {
    let cancelled = false;
    setDangTai(true);
    listEscalations({ patientId: patient.id }, accessToken)
      .then((es) => {
        if (!cancelled) setEscalations(es);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setDangTai(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patient.id, accessToken]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs text-muted-foreground">Tình trạng tuân thủ</p>
        {patient.adherencePct === null ? (
          <p className="mt-1 text-sm text-muted-foreground">Chưa có liều nào đến hạn.</p>
        ) : (
          <>
            <p className="text-sm font-semibold">{patient.adherencePct}%</p>
            <Progress value={patient.adherencePct} className="mt-1 h-2" />
          </>
        )}
      </div>

      <div>
        <h3 className="font-bold">Triệu chứng sức khỏe được báo cáo</h3>
        {!dangTai && escalations.length === 0 && (
          <p className="mt-2 text-sm text-muted-foreground">
            Chưa có triệu chứng/cảnh báo nào được ghi nhận.
          </p>
        )}
        <ul className="mt-2 space-y-2">
          {escalations.map((e) => (
            <li key={e.id} className="rounded-lg border border-border p-3">
              <div className="flex items-center justify-between gap-2">
                <span
                  className={`rounded-md px-2 py-0.5 text-xs font-semibold ${SEVERITY_TONE[e.severity]}`}
                >
                  {e.severity}
                </span>
                <span className="text-xs text-muted-foreground">
                  {new Date(e.createdAt).toLocaleString("vi-VN")}
                </span>
              </div>
              <p className="mt-1.5 text-sm">{e.reason || e.rawUtterance || e.trigger}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function PatientDetail({
  patient,
  onSaved,
}: {
  patient: ReportingPatient;
  onSaved: (patch: PatientHealthPatch) => void;
}) {
  const [tab, setTab] = useState<DetailTab>("health");

  return (
    <div className="mt-5 space-y-4 rounded-lg bg-muted p-4">
      <div role="tablist" className="flex gap-5 border-b border-border text-sm">
        {DETAIL_TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 pb-2.5 font-medium ${
              tab === t.key
                ? "border-primary font-semibold text-primary"
                : "border-transparent text-muted-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "health" && <HealthTab patient={patient} onSaved={onSaved} />}
      {tab === "prescriptions" && (
        <PrescriptionsTab patientId={patient.id} patientName={patient.fullName} />
      )}
      {tab === "adherence" && <AdherenceTab patient={patient} />}
    </div>
  );
}

type WatchFilter = "all" | "watching" | "not_watching";

const WATCH_FILTER_OPTIONS: { value: WatchFilter; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "watching", label: "Đang theo dõi" },
  { value: "not_watching", label: "Không theo dõi" },
];

const PATIENTS_PAGE_SIZE = 10;

function PatientsContent() {
  // ?q= cho phep man hinh khac dan thang toi DUNG mot benh nhan - Hop canh bao
  // (doctor/alerts/page.tsx) gui ma BN qua day tu nut "Hồ sơ đầy đủ" trong
  // popup canh bao. Chi dung lam gia tri KHOI TAO: sau do o tim la cua nguoi
  // dung, khong dong bo nguoc len URL.
  const searchParams = useSearchParams();
  const [q, setQ] = useState(() => searchParams.get("q") ?? "");
  const [watchFilter, setWatchFilter] = useState<WatchFilter>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  // Bat ky bac si nao cung xem/quan ly duoc toan bo benh nhan - tim theo ID
  // hoac ten qua tham so `search` cua backend, debounce de tranh goi API tren
  // tung phim go.
  const [patients, setPatients] = useState<ReportingPatient[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const { accessToken } = useAuth();

  useEffect(() => {
    const timer = setTimeout(() => {
      listReportingPatients(q, accessToken)
        .then(setPatients)
        .catch(() => undefined);
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [q, refreshKey, accessToken]);

  const toggleWatch = async (id: string) => {
    const p = patients.find((x) => x.id === id);
    await setPatientWatch(id, !(p?.watch ?? false), accessToken);
    setRefreshKey((k) => k + 1);
  };

  const filteredPatients = patients.filter((p) => {
    if (watchFilter === "watching") return p.watch;
    if (watchFilter === "not_watching") return !p.watch;
    return true;
  });

  // Phan trang - toi da 10 benh nhan/trang (cung quy uoc voi doctor/page.tsx).
  useEffect(() => {
    setPage(1);
  }, [q, watchFilter]);
  const totalPages = Math.max(1, Math.ceil(filteredPatients.length / PATIENTS_PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages);
  const pagePatients = filteredPatients.slice(
    (pageSafe - 1) * PATIENTS_PAGE_SIZE,
    pageSafe * PATIENTS_PAGE_SIZE,
  );

  const applyHealthPatch = (id: string, patch: PatientHealthPatch) => {
    setPatients((prev) =>
      prev.map((p) =>
        p.id === id
          ? {
              ...p,
              note: patch.note,
              gender: patch.gender,
              heightCm: patch.heightCm,
              weightKg: patch.weightKg,
            }
          : p,
      ),
    );
  };

  return (
    <div className="space-y-6">
      <header className="flex justify-end">
        <div className="flex w-full gap-2 sm:w-auto">
          <Input
            placeholder="Tìm theo tên hoặc ID bệnh nhân…"
            aria-label="Tìm theo tên hoặc ID bệnh nhân"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="w-full sm:w-64"
          />
          <div className="w-40 shrink-0">
            <HoverSelect
              value={watchFilter}
              onChange={(v) => setWatchFilter(v as WatchFilter)}
              options={WATCH_FILTER_OPTIONS}
            />
          </div>
        </div>
      </header>

      <div className="space-y-3">
        {pagePatients.map((p) => {
          const age = tinhTuoi(p.yearOfBirth);
          return (
            <div key={p.id} className="surface-card p-5">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent font-bold text-accent-foreground">
                    {p.fullName.charAt(0)}
                  </span>
                  <div className="min-w-0">
                    <p
                      className="flex items-center gap-2 truncate font-semibold"
                      title={p.fullName}
                    >
                      {p.fullName}
                      {p.watch && (
                        <span className="inline-flex shrink-0 items-center gap-1 rounded bg-warning/25 px-1.5 py-0.5 text-[11px] font-semibold text-warning-foreground">
                          <ShieldAlert className="h-3 w-3" /> Theo dõi
                        </span>
                      )}
                    </p>
                    <p className="truncate text-sm text-muted-foreground">
                      ID: {p.id} {age !== null ? `· ${age} tuổi` : ""}
                    </p>
                  </div>
                </div>
                <div className="grid shrink-0 grid-cols-[6.5rem_7rem] items-center gap-4">
                  <Button
                    variant="outline"
                    size="sm"
                    className="justify-self-start"
                    onClick={() => setOpenId(openId === p.id ? null : p.id)}
                  >
                    <Eye className="mr-1 h-4 w-4" /> Hồ sơ
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="justify-self-start whitespace-nowrap"
                    onClick={() => toggleWatch(p.id)}
                  >
                    {p.watch ? "Bỏ theo dõi" : "Theo dõi"}
                  </Button>
                </div>
              </div>

              {openId === p.id && (
                <PatientDetail patient={p} onSaved={(patch) => applyHealthPatch(p.id, patch)} />
              )}
            </div>
          );
        })}
        {filteredPatients.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Không tìm thấy bệnh nhân phù hợp.
          </p>
        )}
      </div>

      {filteredPatients.length > 0 && (
        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <p>
            Trang {pageSafe}/{totalPages} · {filteredPatients.length} bệnh nhân
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={pageSafe <= 1}
              onClick={() => setPage(pageSafe - 1)}
            >
              Trước
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={pageSafe >= totalPages}
              onClick={() => setPage(pageSafe + 1)}
            >
              Sau
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PatientsPage() {
  // useSearchParams() bat buoc phai nam trong <Suspense> (Next 16) - cung mau
  // voi admin/accounts/page.tsx.
  return (
    <Suspense
      fallback={
        <div className="space-y-6">
          <div className="h-10 w-full animate-pulse rounded-xl bg-muted/40" />
          <div className="h-64 w-full animate-pulse rounded-xl bg-muted/40" />
        </div>
      }
    >
      <PatientsContent />
    </Suspense>
  );
}
