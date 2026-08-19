"use client";

// Tab "Hôm nay" - port tu capyphone.js::renderToday() + renderSheetNotYet()
// + renderFlowConfirm() + renderFlowSuccess(), noi voi du lieu lieu thuoc
// THAT qua lib/doses.
//
// Khac ban mau o cho: moi con so/chu deu tinh tu `doses` that, khong co
// MEDS hard-code, khong co "🔥 7 ngay lien tiep" (chua co gi tinh duoc
// chuoi ngay). Luong camera van dung CameraCapture + VLM that thay cho
// man hinh camera gia cua ban mau.

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Camera, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { CameraCapture } from "@/components/camera-capture";
import {
  CHIP,
  CHIP_THEO_TRANG_THAI,
  CapyPrimaryButton,
  CapySecondaryButton,
  CapySheet,
  PillChip,
  SectionLabel,
  SheetRowButton,
  type ChipStyle,
} from "@/components/capy/capy-ui";
import {
  gioHienThi,
  listDoses,
  pollPhotoVerification,
  submitDosePhoto,
  updateDoseStatus,
  type Dose,
  type PhotoVerification,
} from "@/lib/doses";
import { useAuth } from "@/lib/auth";
import { randomCapyQuote, type CapyQuote } from "@/lib/capy-quotes";

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

function tenThuoc(d: Dose): string {
  return d.expectedItems.map((i) => i.tenThuoc).join(", ") || "Thuốc";
}

function lieuLuong(d: Dose): string {
  return d.expectedItems.map((i) => `${i.soVien} ${i.dangThuoc ?? "đơn vị"}`).join(" · ");
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

// heroMap cua ban goc - giu nguyen mau nen, chip, nhan nut theo tung trang
// thai. Rieng `headline` dung ban "minimal" (khong co tranh Capy).
const HERO: Record<
  TrangThaiHero,
  { bg: string; chip: ChipStyle; headline: string; primary: string; secondary: string }
> = {
  upcoming: {
    bg: "#F4F7FC",
    chip: CHIP.upcoming,
    headline: "Liều tiếp theo",
    primary: "Chụp & xác nhận",
    secondary: "Chưa uống",
  },
  due: {
    bg: "#CFE6FF",
    chip: CHIP.due,
    headline: "Đến giờ uống thuốc",
    primary: "Chụp & xác nhận",
    secondary: "Chưa uống",
  },
  waiting: {
    bg: "#FDEBC9",
    chip: CHIP.waiting,
    headline: "Capy đang chờ xác nhận",
    primary: "Tôi đã uống",
    secondary: "Nhắc lại sau",
  },
  overdue: {
    bg: "#FFD5C2",
    chip: CHIP.overdue,
    headline: "Capy chưa thấy bạn xác nhận",
    primary: "Tôi đã uống",
    secondary: "Nhắc tôi sau",
  },
};

export default function PatientToday() {
  const router = useRouter();
  const { user, accessToken } = useAuth();
  const patientId = user?.patient_id ?? "";

  const [doses, setDoses] = useState<Dose[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [xacMinh, setXacMinh] = useState<PhotoVerification | null>(null);
  const [dangGui, setDangGui] = useState(false);
  const [loiGui, setLoiGui] = useState<string | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  // "Chua uong" chi hoan giao dien - KHONG doi trang thai lieu that trong
  // DB (ADR-0011: chi bam nut moi tinh la bo qua).
  const [daHoan, setDaHoan] = useState<string | null>(null);
  const [sheet, setSheet] = useState<"notyet" | "confirm" | null>(null);
  const [dangXuLy, setDangXuLy] = useState(false);
  // Man hinh "Xong rồi!" sau khi anh khop - giu lai gio ghi nhan THAT va
  // ten thuoc cua lieu VUA xac nhan, vi sau khi tai lai `next` da nhay sang
  // lieu ke tiep (dung bug ma ban goc da ghi chu trong markNext()).
  const [thanhCong, setThanhCong] = useState<{ at: string; line: string } | null>(null);
  // Anh + quote Capy doi ngau nhien moi lan vao lai tab nay. Chon trong
  // useEffect chu khong phai luc render - xem ghi chu o randomCapyQuote().
  const [capy, setCapy] = useState<CapyQuote | null>(null);

  useEffect(() => {
    setCapy(randomCapyQuote());
  }, []);

  const taiLaiDoses = async () => {
    if (!patientId) return;
    setDangTai(true);
    try {
      setDoses(await listDoses(patientId));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được lịch uống thuốc");
    } finally {
      setDangTai(false);
    }
  };

  useEffect(() => {
    taiLaiDoses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  const dosesHomNay = doses.filter((d) => laHomNay(d.scheduledAt));
  const next = dosesHomNay.find((d) => d.status === "PENDING");
  const daXong = dosesHomNay.filter((d) => d.status !== "PENDING").length;
  const tatCaXong = dosesHomNay.length > 0 && !next;
  const lieuMai = doses
    .filter((d) => d.status === "PENDING" && !laHomNay(d.scheduledAt))
    .sort((a, b) => a.scheduledAt.localeCompare(b.scheduledAt))[0];

  const trangThai: TrangThaiHero = (() => {
    if (!next) return "due";
    if (daHoan === next.id) return "waiting";
    const now = Date.now();
    if (now < new Date(next.windowStart).getTime()) return "upcoming";
    if (now > new Date(next.windowEnd).getTime()) return "overdue";
    return "due";
  })();
  const hero = HERO[trangThai];
  const khongCanAnh = trangThai === "overdue" || trangThai === "waiting";

  const cuaSo = (() => {
    if (!next) return "";
    if (trangThai === "waiting") return "đã hoãn • Capy vẫn đang chờ bạn xác nhận";
    if (trangThai === "overdue") {
      const phut = Math.round((Date.now() - new Date(next.windowEnd).getTime()) / 60000);
      return `quá giờ hẹn ${phut} phút • giờ xác nhận thật sẽ được ghi`;
    }
    return `khung xác nhận: ${gioHienThi(next.windowStart)} – ${gioHienThi(next.windowEnd)} • cần ảnh`;
  })();

  const gioSau = (phut: number) =>
    new Date(Date.now() + phut * 60000).toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
    });

  const guiAnh = async (doseId: string, file: File) => {
    const lieu = doses.find((d) => d.id === doseId);
    setDangGui(true);
    setLoiGui(null);
    setXacMinh(null);
    try {
      const daGui = await submitDosePhoto(doseId, file);
      setXacMinh(daGui);
      const ketQua = await pollPhotoVerification(daGui.id, setXacMinh);
      setXacMinh(ketQua);

      // Soan san noi dung man hinh thanh cong, nhung CHI hien sau khi da
      // tai lai danh sach lieu: dong dem "X / Y lieu hom nay" trong do doc
      // tu `doses`, ma luc nay lieu vua xac nhan van con PENDING - hien
      // ngay se ra so cu (vd "1 / 2" thay vi "2 / 2") trong vai tram ms.
      const xong = ketQua.matched
        ? {
            at: gioHienThi(ketQua.createdAt),
            line: lieu
              ? `${tenThuoc(lieu)} · ${lieuLuong(lieu)} • hẹn ${gioHienThi(lieu.scheduledAt)}`
              : "",
          }
        : null;

      if (!ketQua.matched) {
        if (ketQua.nextAction === "CAREGIVER_REVIEW") {
          toast.error("Đã hết lượt chụp lại — chuyển người thân xem giúp");
        } else if (ketQua.status === "loi_he_thong") {
          toast.error("Hệ thống đang bận, bạn thử gửi lại giúp tôi nhé");
        } else {
          toast(ketQua.message);
        }
      }

      await taiLaiDoses();
      if (xong) setThanhCong(xong);
    } catch (err) {
      setLoiGui(err instanceof Error ? err.message : "Không gửi được ảnh");
    } finally {
      setDangGui(false);
    }
  };

  // Tu bao "da uong" KHONG kem anh - chi mo duoc khi qua gio/da hoan.
  // KHONG ghi thang TAKEN: chuyen sang AWAITING_CAREGIVER de nguoi than
  // duyet that o /patient/family/[id].
  const xacNhanKhongAnh = async () => {
    if (!next) return;
    setDangXuLy(true);
    try {
      await updateDoseStatus(next.id, "AWAITING_CAREGIVER", accessToken);
      toast.success("Đã gửi cho người thân xác nhận giúp bạn");
      setSheet(null);
      await taiLaiDoses();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không gửi được yêu cầu xác nhận");
    } finally {
      setDangXuLy(false);
    }
  };

  const boQuaLieu = async () => {
    if (!next) return;
    setDangXuLy(true);
    try {
      await updateDoseStatus(next.id, "MISSED", accessToken);
      toast("Đã ghi nhận bỏ qua liều này");
      setSheet(null);
      await taiLaiDoses();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không ghi được");
    } finally {
      setDangXuLy(false);
    }
  };

  const hoanNhac = () => {
    if (!next) return;
    setDaHoan(next.id);
    setSheet(null);
    toast("Đã hoãn nhắc — liều này vẫn chưa bị tính là bỏ qua");
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Loi chao + tieu de */}
      {user && !dangTai && (
        <div>
          <p className="m-0 text-[13px] font-medium tracking-[.02em] text-[#5B6A85]">
            {loiChao(user.full_name)}
          </p>
          <h1 className="font-display m-0 mt-0.5 text-[30px] font-extrabold leading-[1.1] text-[#16386E]">
            {next ? hero.headline : tatCaXong ? "Hết liều cho hôm nay" : "Hôm nay"}
          </h1>
        </div>
      )}

      {/* Khoi Capy (ban "capyFull" cua thiet ke goc) - anh + quote ngau
          nhien, doi moi lan vao lai tab nay. */}
      {capy && (
        <div className="flex items-center gap-3.5 rounded-[28px] bg-[#CFE6FF] p-4">
          <Image
            src={capy.src}
            alt={capy.alt}
            width={110}
            height={110}
            className="h-[110px] w-[110px] shrink-0 rounded-[24px] object-contain"
            priority
          />
          <div className="min-w-0">
            <p className="font-display m-0 text-[15px] font-bold leading-[1.35] text-[#16386E]">
              {capy.line}
            </p>
            <p className="m-0 mt-1.5 text-[12px] leading-[1.45] text-[#3D5D8C]">{capy.sub}</p>
          </div>
        </div>
      )}

      {dangTai && (
        <div className="flex items-center justify-center gap-2 rounded-[22px] bg-white p-6 text-sm text-[#5B6A85]">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải lịch uống thuốc…
        </div>
      )}

      {/* The lieu chinh */}
      {!dangTai && next && (
        <div className="overflow-hidden rounded-[30px] bg-white shadow-[0_10px_30px_rgba(22,56,110,.07)]">
          <div className="px-5 pb-[18px] pt-5" style={{ background: hero.bg }}>
            <PillChip chip={hero.chip} />
            <p className="font-display m-0 mt-3 text-[46px] font-extrabold leading-none tracking-[-.01em] text-[#16386E]">
              {gioHienThi(next.scheduledAt)}
            </p>
            <p className="font-display m-0 mt-2 text-[20px] font-bold leading-[1.25] text-[#16386E]">
              {tenThuoc(next)}
            </p>
            <p className="m-0 mt-0.5 text-[14px] font-semibold text-[#2F5488]">{lieuLuong(next)}</p>
            {cuaSo && <p className="font-mono m-0 mt-2.5 text-[11px] text-[#5B7098]">{cuaSo}</p>}
          </div>

          <div className="flex flex-col gap-2.5 p-4">
            {dangGui && (
              <div className="flex items-center gap-3 rounded-[16px] bg-[#CFE6FF] p-3 text-sm text-[#16386E]">
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

            {!dangGui && xacMinh && !xacMinh.matched && xacMinh.status !== "dang_xu_ly" && (
              <div
                className="rounded-[16px] p-3 text-sm"
                style={
                  xacMinh.nextAction === "CAREGIVER_REVIEW"
                    ? { background: "#FDEBC9", color: "#8A6516" }
                    : { background: "#F6E1DD", color: "#B4432C" }
                }
              >
                {xacMinh.message}
              </div>
            )}

            {loiGui && (
              <div className="rounded-[16px] bg-[#F6E1DD] p-3 text-sm text-[#B4432C]">{loiGui}</div>
            )}

            {/* Input an - fallback khi trinh duyet khong mo duoc camera */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) guiAnh(next.id, file);
              }}
            />

            <CapyPrimaryButton
              disabled={dangGui}
              onClick={
                xacMinh?.nextAction === "RETAKE" || !khongCanAnh
                  ? () => setCameraOpen(true)
                  : () => setSheet("confirm")
              }
            >
              {dangGui ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  {!khongCanAnh && <Camera className="h-4 w-4" />}
                  {xacMinh?.nextAction === "RETAKE" ? "Chụp lại" : hero.primary}
                </>
              )}
            </CapyPrimaryButton>

            <div className="flex gap-2.5">
              <CapySecondaryButton disabled={dangGui} onClick={() => setSheet("notyet")}>
                {hero.secondary}
              </CapySecondaryButton>
              <CapySecondaryButton
                disabled={dangGui}
                onClick={() => router.push("/patient/assistant")}
              >
                Xem hướng dẫn
              </CapySecondaryButton>
            </div>
          </div>
        </div>
      )}

      <CameraCapture
        open={cameraOpen}
        onOpenChange={setCameraOpen}
        onCapture={(file) => {
          setCameraOpen(false);
          if (next) guiAnh(next.id, file);
        }}
        onFallbackToFile={() => fileInputRef.current?.click()}
      />

      {/* Xong het trong ngay */}
      {!dangTai && tatCaXong && (
        <div className="capy-pop rounded-[30px] bg-[#BFEBDC] px-5 py-[22px] text-center">
          <p className="font-display m-0 text-[26px] font-extrabold leading-[1.15] text-[#14563F]">
            Xong hết rồi! 🎉
          </p>
          <p className="m-0 mt-1.5 text-[14px] leading-[1.5] text-[#1F6A50]">
            Bạn đã hoàn thành tất cả {dosesHomNay.length} liều hôm nay.
            {lieuMai && ` Liều tiếp theo: ${gioHienThi(lieuMai.scheduledAt)} ngày mai.`}
          </p>
          <button
            onClick={() => router.push("/patient/history")}
            className="font-display mt-4 flex min-h-[52px] w-full items-center justify-center rounded-[20px] bg-[#16386E] text-[16px] font-bold text-white transition-colors hover:bg-[#0E2749]"
          >
            Xem tiến độ
          </button>
        </div>
      )}

      {!dangTai && dosesHomNay.length === 0 && (
        <div className="rounded-[22px] bg-white p-6 text-center text-sm text-[#5B6A85]">
          Hôm nay bạn không có liều thuốc nào.
        </div>
      )}

      {/* Thoi khoa bieu */}
      {dosesHomNay.length > 0 && (
        <div>
          <div className="mb-2.5 mt-2">
            <SectionLabel>Thời khoá biểu hôm nay</SectionLabel>
          </div>
          <div className="flex flex-col gap-2.5">
            {dosesHomNay.map((d) => {
              const chip =
                d.id === next?.id ? hero.chip : (CHIP_THEO_TRANG_THAI[d.status] ?? CHIP.upcoming);
              return (
                <div
                  key={d.id}
                  className="grid grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-3 rounded-[22px] bg-white px-4 py-3.5"
                >
                  <span className="font-display text-[15px] font-bold text-[#16386E]">
                    {gioHienThi(d.scheduledAt)}
                  </span>
                  <span className="block min-w-0">
                    <span className="block truncate text-[14px] font-semibold text-[#1B2A44]">
                      {tenThuoc(d)}
                    </span>
                    <span className="block text-[12px] text-[#62708A]">{lieuLuong(d)}</span>
                  </span>
                  <PillChip chip={chip} />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Sheet "Chưa uống được lúc này?" */}
      {sheet === "notyet" && next && (
        <CapySheet onClose={() => setSheet(null)}>
          <p className="font-display m-0 text-[22px] font-extrabold leading-[1.2] text-[#16386E]">
            Chưa uống được lúc này?
          </p>
          <p className="m-0 mt-1.5 text-[13.5px] leading-[1.5] text-[#5B6A85]">
            Liều này vẫn chưa bị tính là bỏ qua.
          </p>
          <div className="mt-[18px] flex flex-col gap-2.5">
            <SheetRowButton label="Nhắc lại sau 10 phút" meta={gioSau(10)} onClick={hoanNhac} />
            <SheetRowButton label="Nhắc lại sau 30 phút" meta={gioSau(30)} onClick={hoanNhac} />
            <SheetRowButton label="Chọn thời gian khác" onClick={() => setSheet(null)} />
            <button
              onClick={boQuaLieu}
              disabled={dangXuLy}
              className="flex min-h-[48px] items-center justify-center rounded-[16px] text-[14px] font-semibold text-[#B4432C] transition-colors hover:bg-[#FBF1EF] disabled:opacity-50"
            >
              Bỏ qua liều này
            </button>
          </div>
        </CapySheet>
      )}

      {/* Sheet xác nhận không cần ảnh */}
      {sheet === "confirm" && next && (
        <CapySheet onClose={() => setSheet(null)}>
          <p className="font-display m-0 text-[24px] font-extrabold leading-[1.2] text-[#16386E]">
            Bạn đã uống liều này chưa?
          </p>
          <div className="mt-3.5 rounded-[20px] bg-[#F4F7FC] p-4">
            <p className="font-display m-0 text-[17px] font-bold text-[#16386E]">
              {tenThuoc(next)} · {lieuLuong(next)}
            </p>
            <p className="m-0 mt-0.5 text-[12.5px] text-[#5B6A85]">
              Hẹn {gioHienThi(next.scheduledAt)} • chưa có ảnh xác nhận
            </p>
          </div>
          <div className="mt-[18px] flex flex-col gap-2.5">
            <CapyPrimaryButton
              disabled={dangXuLy}
              onClick={xacNhanKhongAnh}
              className="min-h-[58px]"
            >
              {dangXuLy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Tôi đã uống ✓"}
            </CapyPrimaryButton>
            <CapySecondaryButton
              disabled={dangXuLy}
              onClick={() => setSheet(null)}
              className="min-h-[50px]"
            >
              Chưa uống
            </CapySecondaryButton>
          </div>
          <p className="font-mono m-0 mt-3.5 text-center text-[11px] leading-[1.5] text-[#5B6A85]">
            Không có ảnh, người thân sẽ xác nhận giúp trước khi tính là đã uống.
          </p>
        </CapySheet>
      )}

      {/* Màn hình thành công sau khi ảnh khớp */}
      {thanhCong && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-[#BFEBDC] p-8 text-center">
          <p className="font-display m-0 text-[30px] font-extrabold leading-[1.15] text-[#14563F]">
            Xong rồi!
          </p>
          <p className="m-0 mt-2 text-[15px] font-medium leading-[1.5] text-[#1F6A50]">
            Capy ghi nhận lúc <strong>{thanhCong.at}</strong> ✨
          </p>
          <p className="m-0 mt-1.5 text-[12.5px] text-[#2F6A54]">{thanhCong.line}</p>
          <p className="font-mono m-0 mt-1 text-[12px] text-[#2F6A54]">
            {daXong} / {dosesHomNay.length} liều hôm nay
          </p>
          <button
            onClick={() => setThanhCong(null)}
            className="font-display mt-[26px] flex min-h-[56px] min-w-[200px] items-center justify-center rounded-[20px] bg-[#16386E] text-[17px] font-bold text-white transition-colors hover:bg-[#0E2749]"
          >
            Về Hôm nay
          </button>
        </div>
      )}
    </div>
  );
}
