"use client";

// Tab "Sức khoẻ" - port tu capyphone.js::renderHealth(), noi voi ho so /
// don thuoc / nhat ky THAT.
//
// Ban mau hard-code "🔥 7 ngay lien tiep" va "tuan thu 7 ngay: 92%".
// O day: so lieu hom nay va ty le tuan thu 7 ngay deu tinh tu `doses` that;
// bo hoan toan phan "chuoi ngay lien tiep" vi chua co gi tinh duoc no.

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Textarea } from "@/components/ui/textarea";
import {
  CHIP,
  CapyPrimaryButton,
  CapySecondaryButton,
  SectionLabel,
  PillChip,
  type ChipStyle,
} from "@/components/capy/capy-ui";
import { useAuth } from "@/lib/auth";
import { listDoses, type Dose } from "@/lib/doses";
import { getMyPatientProfile, type PatientRecord } from "@/lib/patients";
import { listPrescriptions } from "@/lib/prescriptions";
import { reportHealthIssue } from "@/lib/escalations";
import {
  flattenPrescriptions,
  useProto,
  type AlertLevel,
  type Prescription,
} from "@/lib/proto-store";

const MOOD_EMOJI: Record<AlertLevel, string> = { low: "🙂", mid: "😐", high: "😣" };

const CHIP_DON: Record<string, ChipStyle> = {
  approved: { label: "Đang dùng", icon: "●", bg: "#DFF3E9", fg: "#1F6A50" },
  pending: { label: "Chờ duyệt", icon: "‖", bg: "#FDEBC9", fg: "#8A6516" },
};

function trong7Ngay(iso: string): boolean {
  const d = new Date(iso);
  const nay = new Date();
  const dNgay = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const nayNgay = new Date(nay.getFullYear(), nay.getMonth(), nay.getDate()).getTime();
  const cach = Math.round((nayNgay - dNgay) / 86400000);
  return cach >= 0 && cach < 7;
}

function laHomNay(iso: string): boolean {
  const d = new Date(iso);
  const nay = new Date();
  return (
    d.getFullYear() === nay.getFullYear() &&
    d.getMonth() === nay.getMonth() &&
    d.getDate() === nay.getDate()
  );
}

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
  // duoc set. Trang nay tu goi listPrescriptions({patientId}) rieng.
  const [donThuoc, setDonThuoc] = useState<Prescription[]>([]);
  const [dangBao, setDangBao] = useState(false);
  const [text, setText] = useState("");
  const [muc, setMuc] = useState<AlertLevel>("low");

  useEffect(() => {
    if (!patientId) return;
    getMyPatientProfile(accessToken)
      .then(setHoSo)
      .catch(() => undefined);
    listDoses(patientId)
      .then(setDoses)
      .catch(() => undefined);
    listPrescriptions({ patientId })
      .then((records) =>
        setDonThuoc(flattenPrescriptions(records, {}).filter((p) => p.status !== "rejected")),
      )
      .catch(() => undefined);
  }, [patientId, accessToken]);

  const dosesHomNay = doses.filter((d) => laHomNay(d.scheduledAt));
  const daUongHomNay = dosesHomNay.filter(
    (d) => d.status === "TAKEN" || d.status === "DELAYED",
  ).length;

  // Ty le tuan thu 7 ngay: chi tinh cac lieu DA CHOT (uong/tre/bo), khong
  // tinh lieu con PENDING cua tuong lai - neu khong ty le se luon bi thap gia.
  const tuanThu = (() => {
    const daChot = doses.filter(
      (d) => trong7Ngay(d.scheduledAt) && ["TAKEN", "DELAYED", "MISSED"].includes(d.status),
    );
    if (daChot.length === 0) return null;
    const uong = daChot.filter((d) => d.status === "TAKEN" || d.status === "DELAYED").length;
    return Math.round((uong / daChot.length) * 100);
  })();

  const guiBaoVanDe = () => {
    // Nhat ky rieng cua benh nhan (state cuc bo, de tu xem lai) - giu nguyen,
    // KHONG doi. reportHealthIssue() ben duoi la kenh RIENG tao Escalation
    // that cho nguoi than/bac si thay (backend/api/health_log_routes.py) -
    // 2 viec doc lap, loi mang o 1 ben khong duoc chan ben kia.
    reportHealth(text || "Không mô tả chi tiết", muc);
    if (muc === "high") {
      setEmergency(true);
    } else {
      toast(muc === "mid" ? "Đã báo người thân và lưu log vấn đề" : "Đã ghi nhật ký, theo dõi 48h");
    }
    if (muc !== "low" && accessToken) {
      // .catch nuot loi co y - nhat ky cuc bo da ghi xong o tren, khong lam
      // gian doan trai nghiem chi vi 1 loi mang phu.
      const noiDung = text || "Không mô tả chi tiết";
      reportHealthIssue(accessToken, { text: noiDung, level: muc }).catch(() => {});
    }
    setDangBao(false);
    setText("");
    setMuc("low");
  };

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display m-0 mt-1 text-[30px] font-extrabold leading-[1.1] text-[#16386E]">
        Sức khoẻ
      </h1>

      {/* Banner tong quan */}
      {user && (
        <div className="flex items-center gap-3.5 rounded-[28px] bg-[#FFF0D6] p-[18px]">
          <span className="font-display grid h-[72px] w-[72px] shrink-0 place-items-center rounded-[22px] bg-white/70 text-[26px] font-bold text-[#8A6516]">
            {user.full_name.charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="font-display m-0 truncate text-[19px] font-bold text-[#6B4E0E]">
              {user.full_name}
            </p>
            <p className="m-0 mt-0.5 text-[13px] font-semibold text-[#7A5A10]">
              {dosesHomNay.length > 0
                ? `Hôm nay ${daUongHomNay}/${dosesHomNay.length} liều`
                : "Hôm nay chưa có liều nào"}
            </p>
            {tuanThu !== null && (
              <p className="font-mono m-0 mt-1.5 text-[11px] text-[#A07E2E]">
                tuân thủ 7 ngày: {tuanThu}%
              </p>
            )}
            {hoSo?.yearOfBirth && (
              <p className="font-mono m-0 mt-0.5 text-[11px] text-[#A07E2E]">
                {new Date().getFullYear() - hoSo.yearOfBirth} tuổi
              </p>
            )}
          </div>
        </div>
      )}

      {/* Thuoc dang dung - benh nhan chi xem, khong co quyen tu them/sua don
          thuoc (do bac si ke). */}
      <div>
        <div className="mb-2.5">
          <SectionLabel>Thuốc đang dùng</SectionLabel>
        </div>
        <div className="flex flex-col gap-2.5">
          {donThuoc.map((p) => (
            <div key={p.id} className="rounded-[22px] bg-white p-4">
              <div className="flex items-baseline justify-between gap-2.5">
                <p className="font-display m-0 text-[17px] font-bold text-[#16386E]">{p.med}</p>
                <PillChip chip={CHIP_DON[p.status] ?? CHIP.upcoming} />
              </div>
              <p className="m-0 mt-1 text-[13px] text-[#5B6A85]">
                {p.dose} • {p.perDay} lần/ngày • {p.meal}
              </p>
            </div>
          ))}
          {donThuoc.length === 0 && (
            <div className="rounded-[22px] bg-white p-4 text-[13px] text-[#5B6A85]">
              Chưa có đơn thuốc nào.
            </div>
          )}
        </div>
      </div>

      {/* Nhat ky suc khoe */}
      <div>
        <div className="mb-2.5 flex items-baseline justify-between gap-2">
          <SectionLabel>Nhật ký sức khoẻ</SectionLabel>
          {!dangBao && (
            <button
              onClick={() => setDangBao(true)}
              className="font-display rounded-full bg-[#EDF0F6] px-3.5 py-[7px] text-[12px] font-bold text-[#1B2A44] transition-colors hover:bg-[#E3E8F1]"
            >
              + Ghi nhật ký
            </button>
          )}
        </div>

        {dangBao && (
          <div className="mb-2.5 flex flex-col gap-3 rounded-[22px] bg-white p-4">
            <Textarea
              rows={3}
              placeholder="Ví dụ: chóng mặt, buồn nôn sau khi uống thuốc…"
              aria-label="Mô tả vấn đề sức khỏe"
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="rounded-2xl border-[#E3E8F1]"
            />
            <div role="radiogroup" aria-label="Mức độ nghiêm trọng" className="grid grid-cols-3 gap-2">
              {(
                [
                  ["low", "Nhẹ"],
                  ["mid", "Trung bình"],
                  ["high", "Nghiêm trọng"],
                ] as [AlertLevel, string][]
              ).map(([v, label]) => (
                <button
                  key={v}
                  role="radio"
                  aria-checked={muc === v}
                  onClick={() => setMuc(v)}
                  className="rounded-2xl border py-2.5 text-[13px] font-semibold transition-colors"
                  style={
                    muc === v
                      ? { borderColor: "#16386E", background: "#CFE6FF", color: "#16386E" }
                      : { borderColor: "#E3E8F1", color: "#5B6A85" }
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex gap-2.5">
              <CapySecondaryButton onClick={() => setDangBao(false)}>Huỷ</CapySecondaryButton>
              <CapyPrimaryButton className="min-h-[48px] flex-1 text-[15px]" onClick={guiBaoVanDe}>
                Gửi
              </CapyPrimaryButton>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-2.5">
          {healthLog.map((h) => (
            <div
              key={h.id}
              className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-3 rounded-[22px] bg-white px-4 py-3.5"
            >
              <span className="text-[22px] leading-none">{MOOD_EMOJI[h.level] ?? "🙂"}</span>
              <span className="block min-w-0">
                <span className="block text-[14px] font-semibold">{h.text}</span>
                <span className="block text-[12px] leading-[1.45] text-[#5B6A85]">{h.at}</span>
              </span>
            </div>
          ))}
          {healthLog.length === 0 && !dangBao && (
            <div className="rounded-[22px] bg-white p-4 text-[13px] text-[#5B6A85]">
              Chưa có nhật ký nào.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
