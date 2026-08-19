"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Clock,
  Loader2,
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
  type Dose,
  type PhotoVerification,
} from "@/lib/doses";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

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

export default function PatientToday() {
  const router = useRouter();
  const { reportHealth, requestSymptomCheck } = useProto();
  const { user } = useAuth();
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

  return (
    <div className="space-y-4">
      {dangTaiDoses ? (
        <section className="surface-card flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải lịch uống thuốc…
        </section>
      ) : next ? (
        <section className="surface-card overflow-hidden">
          <div className="brand-gradient p-5 text-primary-foreground">
            <p className="text-sm opacity-85">Đến giờ uống thuốc</p>
            <p className="text-4xl font-extrabold">{gioHienThi(next.scheduledAt)}</p>
            <p className="mt-1 text-sm opacity-90">{moTaThuoc(next)}</p>
          </div>
          <div className="space-y-4 p-5">
            {!xacMinh && !dangGui && (
              <p className="rounded-lg bg-accent p-3 text-sm text-accent-foreground">
                Hãy bày thuốc ra và chụp một ảnh để xác nhận đã uống. Khung an toàn còn ±30 phút
                quanh giờ hẹn.
              </p>
            )}

            {dangGui && (
              <div className="flex items-center gap-3 rounded-lg bg-accent p-3 text-sm text-accent-foreground">
                <Loader2 className="h-5 w-5 shrink-0 animate-spin" />
                <span>
                  {xacMinh?.message ??
                    "Đang phân tích ảnh, việc này có thể mất vài phút — bác cứ để yên máy."}
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
              <Button size="lg" className="w-full" disabled={dangGui} onClick={moCamera}>
                {dangGui ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Camera className="mr-1 h-4 w-4" />
                )}
                {xacMinh?.nextAction === "RETAKE" ? "Chụp lại" : "Chụp ảnh xác nhận đã uống"}
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

            <Button
              variant="outline"
              className="w-full"
              disabled={dangGui}
              onClick={() => toast("Xác nhận bằng nút bấm chưa nối API — sắp có")}
            >
              <Clock className="mr-1 h-4 w-4" /> Chưa uống
            </Button>
          </div>
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
          <h2 className="text-sm font-bold uppercase text-muted-foreground">
            Thời khóa biểu hôm nay
          </h2>
          {dosesHomNay.map((d) => (
            <div key={d.id} className="surface-card p-4">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                <div className="min-w-0">
                  <p className="truncate font-semibold" title={`${gioHienThi(d.scheduledAt)} · ${moTaThuoc(d)}`}>
                    {gioHienThi(d.scheduledAt)} · {moTaThuoc(d)}
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
                          : "bg-secondary text-secondary-foreground"
                  }`}
                >
                  {NHAN_TRANG_THAI_LIEU[d.status] ?? d.status}
                </span>
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
