"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Clock,
  Loader2,
  PartyPopper,
  Smile,
  ThumbsUp,
  Users,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { CameraCapture } from "@/components/camera-capture";
import {
  gioHienThi,
  listDoses,
  moTaThuoc,
  NHAN_TRANG_THAI_LIEU,
  pollPhotoVerification,
  submitDosePhoto,
  updateDoseStatus,
  type Dose,
  type PhotoVerification,
} from "@/lib/doses";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

// Sheet day len tu day man hinh - dung chung cho "hoan nhac" va "xac nhan
// khong anh", giong pattern overlay()/sheetHandle() cua ban thiet ke goc.
function BottomSheet({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <div className="absolute inset-0 bg-[rgba(15,26,45,.42)]" onClick={onClose} />
      <div className="relative w-full max-w-[430px] rounded-t-[32px] bg-card p-[22px_20px_30px]">
        <span className="mx-auto mb-4 block h-[5px] w-11 rounded-full bg-[#E3E8F1]" />
        {children}
      </div>
    </div>
  );
}

// GET /api/v1/doses tra ve TOAN BO lich (ke ca cac ngay tuong lai - moi don
// mac dinh sinh 7 ngay, xem SO_NGAY_MAC_DINH trong service.py), khong loc
// theo ngay. "Thoi khoa bieu hom nay" phai tu loc lai o day - so sanh theo
// ngay-thang cuc bo cua trinh duyet (may nguoi dung dat gio VN) chu khong
// phai ngay UTC, vi mot lieu 08:00 VN la 01:00 UTC hom sau/truoc bien gioi
// ngay UTC.
function laHomNay(iso: string): boolean {
  const d = new Date(iso);
  const nay = new Date();
  return (
    d.getFullYear() === nay.getFullYear() &&
    d.getMonth() === nay.getMonth() &&
    d.getDate() === nay.getDate()
  );
}

function loiChao(ten: string): string {
  const h = new Date().getHours();
  const first = ten.trim().split(/\s+/).pop() ?? ten;
  if (h < 11) return `Chào buổi sáng, ${first} ☀️`;
  if (h < 13) return `Chào buổi trưa, ${first} 🌤️`;
  if (h < 18) return `Chào buổi chiều, ${first}`;
  return `Chào buổi tối, ${first} 🌙`;
}

type TrangThaiHero = "upcoming" | "due" | "waiting" | "overdue";

const HERO_META: Record<
  TrangThaiHero,
  {
    heroBg: string;
    chipBg: string;
    chipFg: string;
    chipLabel: string;
    headline: string;
    primaryLabel: string;
    secondaryLabel: string;
  }
> = {
  upcoming: {
    heroBg: "#F4F7FC",
    chipBg: "#EDF0F6",
    chipFg: "#5B6A85",
    chipLabel: "◦ Sắp tới",
    headline: "Liều tiếp theo",
    primaryLabel: "Chụp & xác nhận",
    secondaryLabel: "Chưa uống",
  },
  due: {
    heroBg: "#CFE6FF",
    chipBg: "#16386E",
    chipFg: "#FFFFFF",
    chipLabel: "● Đến giờ",
    headline: "Đến giờ uống thuốc",
    primaryLabel: "Chụp & xác nhận",
    secondaryLabel: "Chưa uống",
  },
  waiting: {
    heroBg: "#FDEBC9",
    chipBg: "#FDEBC9",
    chipFg: "#8A6516",
    chipLabel: "◑ Chờ xác nhận",
    headline: "Capy đang chờ xác nhận",
    primaryLabel: "Tôi đã uống",
    secondaryLabel: "Nhắc lại sau",
  },
  overdue: {
    heroBg: "#FFD5C2",
    chipBg: "#F6E1DD",
    chipFg: "#B4432C",
    chipLabel: "! Quá giờ",
    headline: "Capy chưa thấy bạn xác nhận",
    primaryLabel: "Tôi đã uống",
    secondaryLabel: "Nhắc tôi sau",
  },
};

export default function PatientToday() {
  const router = useRouter();
  const { reportHealth, requestSymptomCheck } = useProto();
  const { user, accessToken } = useAuth();
  const patientId = user?.patient_id ?? "";
  const [checkinDone, setCheckinDone] = useState(false);

  const [doses, setDoses] = useState<Dose[]>([]);
  const [dangTaiDoses, setDangTaiDoses] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Ket qua lan xac minh gan nhat CHO DOSE DANG HIEN (khong phai lich su ca
  // ngay) - reset ve null moi khi doi sang lieu khac hoac tai lai danh sach.
  const [xacMinh, setXacMinh] = useState<PhotoVerification | null>(null);
  const [dangGui, setDangGui] = useState(false);
  const [loiGui, setLoiGui] = useState<string | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  // "Chua uong" chi hoan giao dien (nhac lai sau) - KHONG doi trang thai
  // lieu that trong DB, dung y nguyen tac ADR-0011: chi bam nut moi tinh la
  // bo qua. Reset khi doi sang lieu khac (id lieu thay doi).
  const [daHoan, setDaHoan] = useState<string | null>(null);
  const [sheet, setSheet] = useState<"snooze" | "confirm" | null>(null);
  const [dangXuLyKhongAnh, setDangXuLyKhongAnh] = useState(false);

  const taiLaiDoses = async () => {
    if (!patientId) return;
    setDangTaiDoses(true);
    try {
      setDoses(await listDoses(patientId));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được lịch uống thuốc");
    } finally {
      setDangTaiDoses(false);
    }
  };

  useEffect(() => {
    taiLaiDoses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  const dosesHomNay = doses.filter((d) => laHomNay(d.scheduledAt));
  const next = dosesHomNay.find((d) => d.status === "PENDING");
  const daXongCount = dosesHomNay.filter((d) => d.status !== "PENDING").length;
  const tatCaXong = dosesHomNay.length > 0 && !next;
  const lieuTiepTheo = doses
    .filter((d) => d.status === "PENDING" && !laHomNay(d.scheduledAt))
    .sort((a, b) => a.scheduledAt.localeCompare(b.scheduledAt))[0];

  const trangThaiHero: TrangThaiHero = (() => {
    if (!next) return "due";
    if (daHoan === next.id) return "waiting";
    const now = Date.now();
    const start = new Date(next.windowStart).getTime();
    const end = new Date(next.windowEnd).getTime();
    if (now < start) return "upcoming";
    if (now > end) return "overdue";
    return "due";
  })();
  const meta = HERO_META[trangThaiHero];

  const cuaSoText = (() => {
    if (!next) return "";
    if (trangThaiHero === "waiting") return "đã hoãn • Capy vẫn đang chờ bạn xác nhận";
    if (trangThaiHero === "overdue") {
      const phutQua = Math.round((Date.now() - new Date(next.windowEnd).getTime()) / 60000);
      return `quá giờ hẹn ${phutQua} phút • giờ xác nhận thật sẽ được ghi`;
    }
    return `khung xác nhận: ${gioHienThi(next.windowStart)} – ${gioHienThi(next.windowEnd)} • cần ảnh`;
  })();

  const moCamera = () => setCameraOpen(true);
  const chonAnh = () => fileInputRef.current?.click();

  const guiAnh = async (doseId: string, file: File) => {
    setDangGui(true);
    setLoiGui(null);
    setXacMinh(null);
    try {
      const daGui = await submitDosePhoto(doseId, file);
      setXacMinh(daGui);
      const ketQuaCuoi = await pollPhotoVerification(daGui.id, setXacMinh);
      setXacMinh(ketQuaCuoi);
      if (ketQuaCuoi.matched) {
        toast.success("Ảnh khớp đơn thuốc — đã ghi nhận ĐÃ UỐNG");
      } else if (ketQuaCuoi.nextAction === "CAREGIVER_REVIEW") {
        toast.error("Đã hết lượt chụp lại — chuyển người thân xem giúp");
      } else if (ketQuaCuoi.status === "loi_he_thong") {
        toast.error("Hệ thống bận, bác thử gửi lại giúp cháu nhé");
      } else {
        toast(ketQuaCuoi.message);
      }
      await taiLaiDoses();
    } catch (err) {
      setLoiGui(err instanceof Error ? err.message : "Không gửi được ảnh");
    } finally {
      setDangGui(false);
    }
  };

  // Tu bao "da uong" KHONG kem anh - dung khi qua giop/da hoan va benh nhan
  // khong the/khong muon chup lai. KHONG ghi thang TAKEN - chuyen sang
  // AWAITING_CAREGIVER (dung endpoint PATCH /api/doses/{id} da co san quyen
  // cho patient tu doi trang thai lieu cua chinh minh) de nguoi than duyet
  // that qua man "Duyet uong thuoc" (frontend/src/app/patient/family/[id]/
  // page.tsx) - giu nguyen tac "khong tu dong tin", chi la doi ai xac minh
  // (AI qua anh, hay nguoi than qua mat) chu khong bo qua xac minh.
  const xacNhanKhongAnh = async () => {
    if (!next) return;
    setDangXuLyKhongAnh(true);
    try {
      await updateDoseStatus(next.id, "AWAITING_CAREGIVER", accessToken);
      toast.success("Đã gửi cho người thân xác nhận giúp bạn");
      setSheet(null);
      await taiLaiDoses();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không gửi được yêu cầu xác nhận");
    } finally {
      setDangXuLyKhongAnh(false);
    }
  };

  const boQuaLieu = async () => {
    if (!next) return;
    setDangXuLyKhongAnh(true);
    try {
      await updateDoseStatus(next.id, "MISSED", accessToken);
      toast("Đã ghi nhận bỏ qua liều này");
      setSheet(null);
      await taiLaiDoses();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không ghi được");
    } finally {
      setDangXuLyKhongAnh(false);
    }
  };

  const gioSau = (phut: number) => {
    const t = new Date(Date.now() + phut * 60000);
    return t.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="space-y-4">
      {user && !dangTaiDoses && (next || tatCaXong) && (
        <p className="text-[13px] font-medium text-[#5B6A85]">{loiChao(user.full_name)}</p>
      )}

      {dosesHomNay.length > 0 && (
        <button
          onClick={() => router.push("/patient/history")}
          className="w-full rounded-[22px] bg-card p-[14px_16px] text-left shadow-[var(--shadow-card)]"
        >
          <div className="flex items-center justify-between gap-2">
            <p className="text-[13px] font-semibold text-foreground">
              {daXongCount} / {dosesHomNay.length} liều đã hoàn thành
            </p>
            <span className="font-mono text-[11px] text-[#62708A]">xem tiến độ ›</span>
          </div>
          <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-[#EDF0F6]">
            <div
              className="h-full rounded-full bg-[#2E9E6B]"
              style={{ width: `${(daXongCount / dosesHomNay.length) * 100}%` }}
            />
          </div>
        </button>
      )}

      {dangTaiDoses ? (
        <section className="surface-card flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải lịch uống thuốc…
        </section>
      ) : next ? (
        <section className="overflow-hidden rounded-[30px] bg-card shadow-[0_10px_30px_rgba(22,56,110,.07)]">
          <div className="p-[20px_20px_18px]" style={{ backgroundColor: meta.heroBg }}>
            <span
              className="inline-block rounded-full px-3 py-1.5 text-[12px] font-bold"
              style={{ backgroundColor: meta.chipBg, color: meta.chipFg }}
            >
              {meta.chipLabel}
            </span>
            <p className="font-display mt-2 text-[30px] font-extrabold leading-[1.1] text-[#16386E]">
              {meta.headline}
            </p>
            <p className="font-display mt-1 text-[46px] font-extrabold leading-none text-[#16386E]">
              {gioHienThi(next.scheduledAt)}
            </p>
            <p className="mt-1 text-[20px] font-bold leading-[1.25] text-[#16386E]">
              {moTaThuoc(next)}
            </p>
            {cuaSoText && (
              <p className="font-mono mt-1.5 text-[11px] text-[#5B7098]">{cuaSoText}</p>
            )}
          </div>
          <div className="space-y-3 p-4">
            {!xacMinh && !dangGui && (
              <p className="rounded-lg bg-accent p-3 text-sm text-accent-foreground">
                Bày thuốc ra và chụp một tấm ảnh để xác nhận đã uống nhé — bạn có thể chụp trong
                khoảng ±30 phút quanh giờ hẹn.
              </p>
            )}

            {dangGui && (
              <div className="flex items-center gap-3 rounded-lg bg-accent p-3 text-sm text-accent-foreground">
                <Loader2 className="h-5 w-5 shrink-0 animate-spin" />
                <span>
                  {xacMinh?.message ??
                    "Đang phân tích ảnh, việc này có thể mất vài phút — bạn cứ để yên máy."}
                  {xacMinh && xacMinh.attempt > 0 && (
                    <span className="block text-xs opacity-75">
                      Lần {xacMinh.attempt}/{xacMinh.maxAttempts}
                    </span>
                  )}
                </span>
              </div>
            )}

            {!dangGui && xacMinh && xacMinh.status !== "dang_xu_ly" && (
              <div
                className={`flex items-start gap-3 rounded-lg p-3 text-sm ${
                  xacMinh.matched
                    ? "bg-success/15 text-success"
                    : xacMinh.nextAction === "CAREGIVER_REVIEW"
                      ? "bg-warning/25 text-warning-foreground"
                      : "bg-destructive/15 text-destructive"
                }`}
              >
                {xacMinh.matched ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                ) : xacMinh.nextAction === "CAREGIVER_REVIEW" ? (
                  <Users className="mt-0.5 h-4 w-4 shrink-0" />
                ) : (
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
                )}
                <span>{xacMinh.message}</span>
              </div>
            )}

            {loiGui && (
              <div className="flex items-start gap-3 rounded-lg bg-destructive/15 p-3 text-sm text-destructive">
                <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{loiGui}</span>
              </div>
            )}

            {/* Ẩn input thật, dùng nút bấm để kích hoạt — accept+capture mở
                thẳng camera trên điện thoại, mở hộp chọn file trên máy tính. */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = ""; // cho chọn lại cùng 1 file lần sau
                if (file) guiAnh(next.id, file);
              }}
            />

            {(!xacMinh || xacMinh.nextAction === "RETAKE" || xacMinh.status === "loi_he_thong") && (
              <Button
                size="lg"
                className="h-14 w-full rounded-[20px] text-[17px]"
                disabled={dangGui}
                onClick={
                  xacMinh?.nextAction !== "RETAKE" &&
                  (trangThaiHero === "overdue" || trangThaiHero === "waiting")
                    ? () => setSheet("confirm")
                    : moCamera
                }
              >
                {dangGui ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Camera className="mr-1 h-4 w-4" />
                )}
                {xacMinh?.nextAction === "RETAKE" ? "Chụp lại" : meta.primaryLabel}
              </Button>
            )}

            <CameraCapture
              open={cameraOpen}
              onOpenChange={setCameraOpen}
              onCapture={(file) => {
                setCameraOpen(false);
                guiAnh(next.id, file);
              }}
              onFallbackToFile={chonAnh}
            />

            {daHoan !== next.id && (
              <Button
                variant="outline"
                className="h-12 w-full rounded-[18px] bg-[#EDF0F6]"
                disabled={dangGui}
                onClick={() => setSheet("snooze")}
              >
                <Clock className="mr-1 h-4 w-4" /> {meta.secondaryLabel}
              </Button>
            )}
          </div>
        </section>
      ) : tatCaXong ? (
        <section
          className="rounded-[30px] p-[22px_20px] text-center"
          style={{ backgroundColor: "var(--capy-mint)" }}
        >
          <PartyPopper className="mx-auto h-9 w-9" style={{ color: "#14563F" }} />
          <p className="font-display mt-2 text-[26px] font-extrabold leading-[1.15] text-[#14563F]">
            Xong hết rồi! 🎉
          </p>
          <p className="mt-2 text-[14px] leading-[1.5] text-[#1F6A50]">
            Bạn đã hoàn thành tất cả {dosesHomNay.length} liều hôm nay.
            {lieuTiepTheo &&
              ` Liều tiếp theo: ${gioHienThi(lieuTiepTheo.scheduledAt)} ${
                laHomNay(lieuTiepTheo.scheduledAt) ? "hôm nay" : "ngày mai"
              }.`}
          </p>
          <Button
            className="mt-4 h-[52px] w-full rounded-[20px]"
            onClick={() => router.push("/patient/history")}
          >
            Xem tiến độ
          </Button>
        </section>
      ) : checkinDone ? (
        <section className="surface-card p-6 text-center">
          <CheckCircle2 className="mx-auto h-10 w-10 text-success" />
          <p className="mt-3 font-bold">Hôm nay bạn đã xử lý hết các liều</p>
          <p className="text-sm text-muted-foreground">Chúng tôi sẽ nhắc bạn ở liều tiếp theo.</p>
        </section>
      ) : (
        <section className="surface-card p-5 text-center">
          <Smile className="mx-auto h-10 w-10 text-primary" />
          <h1 className="mt-3 text-xl font-extrabold">Hôm nay bạn thấy thế nào?</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Câu trả lời giúp bác sĩ và người thân theo dõi tình trạng của bạn.
          </p>
          <div className="mt-5 space-y-3">
            <Button
              className="w-full"
              size="lg"
              onClick={() => {
                reportHealth("Bình thường", "low");
                toast.success("Đã ghi nhận: bình thường");
                setCheckinDone(true);
              }}
            >
              <ThumbsUp className="mr-1 h-4 w-4" /> Bình thường
            </Button>
            <Button
              variant="outline"
              className="w-full"
              size="lg"
              onClick={() => {
                requestSymptomCheck();
                router.push("/patient/assistant");
              }}
            >
              <AlertTriangle className="mr-1 h-4 w-4" /> Không ổn
            </Button>
          </div>
        </section>
      )}

      {dosesHomNay.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-[12px] font-bold uppercase tracking-[0.1em] text-[#62708A]">
            Thời khóa biểu hôm nay
          </h2>
          {dosesHomNay.map((d) => (
            <div
              key={d.id}
              className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[22px] bg-card p-4 shadow-[var(--shadow-card)]"
            >
              <div className="min-w-0">
                <p className="truncate text-[14px] font-semibold">
                  <span className="font-mono">{gioHienThi(d.scheduledAt)}</span> · {moTaThuoc(d)}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${
                  d.status === "TAKEN" || d.status === "DELAYED"
                    ? "bg-success/15 text-success"
                    : d.status === "MISSED"
                      ? "bg-destructive/15 text-destructive"
                      : d.status === "AWAITING_CAREGIVER"
                        ? "bg-warning/25 text-warning-foreground"
                        : d.id === next?.id
                          ? "font-bold"
                          : "bg-secondary text-secondary-foreground"
                }`}
                style={
                  d.id === next?.id && d.status === "PENDING"
                    ? { backgroundColor: meta.chipBg, color: meta.chipFg }
                    : undefined
                }
              >
                {d.id === next?.id && d.status === "PENDING"
                  ? meta.chipLabel.replace(/^[●◦◑!]\s*/, "")
                  : (NHAN_TRANG_THAI_LIEU[d.status] ?? d.status)}
              </span>
            </div>
          ))}
        </section>
      )}

      {sheet === "snooze" && next && (
        <BottomSheet onClose={() => setSheet(null)}>
          <p className="font-display text-[22px] font-extrabold leading-[1.2] text-[#16386E]">
            Chưa uống được lúc này?
          </p>
          <p className="mt-1.5 text-[13.5px] leading-[1.5] text-[#5B6A85]">
            Liều này vẫn chưa bị tính là bỏ qua.
          </p>
          <div className="mt-[18px] flex flex-col gap-2.5">
            <button
              className="flex min-h-[54px] items-center justify-between rounded-[18px] bg-[#EDF0F6] px-[18px] text-[15px] font-semibold text-[#1B2A44]"
              onClick={() => {
                setDaHoan(next.id);
                setSheet(null);
                toast("Đã hoãn nhắc — liều này vẫn chưa bị tính là bỏ qua");
              }}
            >
              Nhắc lại sau 10 phút
              <span className="font-mono text-[12px] text-[#62708A]">{gioSau(10)}</span>
            </button>
            <button
              className="flex min-h-[54px] items-center justify-between rounded-[18px] bg-[#EDF0F6] px-[18px] text-[15px] font-semibold text-[#1B2A44]"
              onClick={() => {
                setDaHoan(next.id);
                setSheet(null);
                toast("Đã hoãn nhắc — liều này vẫn chưa bị tính là bỏ qua");
              }}
            >
              Nhắc lại sau 30 phút
              <span className="font-mono text-[12px] text-[#62708A]">{gioSau(30)}</span>
            </button>
            <button
              className="flex min-h-[54px] items-center justify-center rounded-[18px] bg-[#EDF0F6] px-[18px] text-[15px] font-semibold text-[#1B2A44]"
              onClick={() => setSheet(null)}
            >
              Chọn thời gian khác
            </button>
            <button
              className="flex min-h-[48px] items-center justify-center rounded-2xl text-[14px] font-semibold text-destructive disabled:opacity-50"
              disabled={dangXuLyKhongAnh}
              onClick={boQuaLieu}
            >
              Bỏ qua liều này
            </button>
          </div>
        </BottomSheet>
      )}

      {sheet === "confirm" && next && (
        <BottomSheet onClose={() => setSheet(null)}>
          <p className="font-display text-[24px] font-extrabold leading-[1.2] text-[#16386E]">
            Bạn đã uống liều này chưa?
          </p>
          <div className="mt-3.5 rounded-[20px] bg-[#F4F7FC] p-4">
            <p className="font-display text-[17px] font-bold text-[#16386E]">{moTaThuoc(next)}</p>
            <p className="mt-1 text-[12.5px] text-[#5B6A85]">
              Hẹn {gioHienThi(next.scheduledAt)} • chưa có ảnh xác nhận
            </p>
          </div>
          <div className="mt-[18px] flex flex-col gap-2.5">
            <Button
              className="h-[58px] rounded-[20px] text-[17px]"
              disabled={dangXuLyKhongAnh}
              onClick={xacNhanKhongAnh}
            >
              {dangXuLyKhongAnh ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                "Tôi đã uống ✓"
              )}
            </Button>
            <Button
              variant="outline"
              className="h-[50px] rounded-[18px] bg-[#EDF0F6]"
              disabled={dangXuLyKhongAnh}
              onClick={() => setSheet(null)}
            >
              Chưa uống
            </Button>
          </div>
          <p className="font-mono mt-3.5 text-center text-[11px] leading-[1.5] text-[#5B6A85]">
            Không có ảnh, người thân của bạn sẽ xác nhận giúp trước khi tính là đã uống.
          </p>
        </BottomSheet>
      )}
    </div>
  );
}
