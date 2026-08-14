"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, HeartPulse, Pill } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";
import { listDoses, type Dose } from "@/lib/doses";
import { getMyPatientProfile, type PatientRecord } from "@/lib/patients";
import { listPrescriptions } from "@/lib/prescriptions";
import { flattenPrescriptions, useProto, type AlertLevel, type Prescription } from "@/lib/proto-store";

export default function HealthPage() {
  const { healthLog, reportHealth, setEmergency } = useProto();
  const { user, accessToken } = useAuth();
  const patientId = user?.patient_id ?? "";
  const [hoSo, setHoSo] = useState<PatientRecord | null>(null);
  const [doses, setDoses] = useState<Dose[]>([]);
  // Vong nay (2026-08-14): KHONG dung `prescriptions` cua useProto() nua -
  // refreshPrescriptions() cua store do goi keo listPatients() (chi
  // doctor/admin, 403 voi role=patient) qua Promise.all, nen voi tai khoan
  // benh nhan promise do LUON reject va prescriptions o store KHONG BAO GIO
  // duoc set (rong vinh vien du DB co don active that - bug that, xac nhan
  // qua DB production: BN-0000 co 4 don active nhung UI hien "chua co don
  // thuoc nao"). Trang nay tu goi listPrescriptions({patientId}) rieng - da
  // loc dung 1 benh nhan o tang backend, khong can tra ten qua listPatients().
  const [myPrescriptions, setMyPrescriptions] = useState<Prescription[]>([]);
  const [reporting, setReporting] = useState(false);
  const [text, setText] = useState("");
  const [level, setLevel] = useState<AlertLevel>("low");

  useEffect(() => {
    if (!patientId) return;
    // Cung ly do voi prescriptions o tren: listPatients() 403 voi
    // role=patient - dung getMyPatientProfile() (GET /api/patients/me,
    // backend tu doc patient_id qua JWT) thay vi tim trong toan bo danh
    // sach chi doctor/admin xem duoc.
    getMyPatientProfile(accessToken)
      .then(setHoSo)
      .catch(() => undefined);
    listDoses(patientId)
      .then(setDoses)
      .catch(() => undefined);
    listPrescriptions({ patientId })
      .then((records) => setMyPrescriptions(flattenPrescriptions(records, {}).filter((p) => p.status !== "rejected")))
      .catch(() => undefined);
  }, [patientId, accessToken]);

  const takenCount = doses.filter((d) => d.status === "TAKEN" || d.status === "DELAYED").length;

  const submit = () => {
    reportHealth(text || "Không mô tả chi tiết", level);
    if (level === "high") {
      setEmergency(true);
    } else {
      toast(
        level === "mid" ? "Đã báo người thân và lưu log vấn đề" : "Đã ghi nhật ký, theo dõi 48h",
      );
    }
    setReporting(false);
    setText("");
    setLevel("low");
  };

  return (
    <div className="space-y-4">
      {user && (
        <section className="surface-card p-5">
          <div className="flex items-center gap-3">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent text-lg font-bold text-accent-foreground">
              {user.full_name.charAt(0)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-bold">{user.full_name}</p>
              <p className="truncate text-sm text-muted-foreground">
                {[
                  hoSo?.yearOfBirth ? `${new Date().getFullYear() - hoSo.yearOfBirth} tuổi` : null,
                  hoSo?.note,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
          </div>
          {doses.length > 0 && (
            <p className="mt-3 text-[11px] text-muted-foreground">
              Đã uống {takenCount}/{doses.length} liều hôm nay
            </p>
          )}
        </section>
      )}

      <section className="surface-card p-5">
        <h2 className="flex items-center gap-2 text-sm font-bold uppercase text-muted-foreground">
          <Pill className="h-4 w-4" /> Đơn thuốc hiện tại
        </h2>
        <div className="mt-3 divide-y divide-border">
          {myPrescriptions.map((p) => (
            <div key={p.id} className="py-3">
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold">{p.med}</p>
                <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-bold text-secondary-foreground">
                  {p.status === "approved"
                    ? "Đang dùng"
                    : p.status === "pending"
                      ? "Chờ duyệt"
                      : "Bản nháp"}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {p.dose} · {p.perDay} lần/ngày · {p.meal}
              </p>
            </div>
          ))}
          {myPrescriptions.length === 0 && (
            <p className="py-3 text-sm text-muted-foreground">Chưa có đơn thuốc nào.</p>
          )}
        </div>
      </section>

      <section className="surface-card space-y-3 p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-sm font-bold uppercase text-muted-foreground">
            <HeartPulse className="h-4 w-4" /> Nhật ký sức khỏe
          </h2>
          {!reporting && (
            <Button size="sm" variant="outline" onClick={() => setReporting(true)}>
              <AlertTriangle className="mr-1 h-4 w-4" /> Báo vấn đề
            </Button>
          )}
        </div>

        {reporting && (
          <div className="space-y-3 rounded-xl border border-border p-4">
            <Textarea
              rows={3}
              placeholder="Ví dụ: chóng mặt, buồn nôn sau khi uống thuốc…"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  ["low", "Nhẹ"],
                  ["mid", "Trung bình"],
                  ["high", "Nghiêm trọng"],
                ] as [AlertLevel, string][]
              ).map(([v, label]) => (
                <button
                  key={v}
                  onClick={() => setLevel(v)}
                  className={`rounded-lg border p-2 text-sm font-semibold transition-colors ${
                    level === v
                      ? "border-primary bg-accent text-accent-foreground"
                      : "border-border"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={() => setReporting(false)}>
                Hủy
              </Button>
              <Button onClick={submit}>Gửi</Button>
            </div>
          </div>
        )}

        {healthLog.length === 0 && !reporting && (
          <p className="text-sm text-muted-foreground">Chưa có nhật ký nào.</p>
        )}
        {healthLog.length > 0 && (
          <ul className="space-y-2 text-sm">
            {healthLog.map((h) => (
              <li key={h.id} className="flex gap-3">
                <span className="w-12 shrink-0 font-mono text-xs text-muted-foreground">
                  {h.at}
                </span>
                <span className="min-w-0">{h.text}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
