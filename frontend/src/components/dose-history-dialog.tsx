"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, HelpCircle, ImageOff, Loader2, XCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  gioHienThi,
  listPhotoVerifications,
  moTaThuoc,
  ngayHienThi,
  photoVerificationImageUrl,
  type Dose,
  type PhotoVerification,
} from "@/lib/doses";

const NHAN_KET_QUA: Record<PhotoVerification["status"], string> = {
  dang_xu_ly: "Đang phân tích",
  khop: "Khớp đơn thuốc",
  lech: "Không khớp đơn thuốc",
  khong_xac_minh_duoc: "Không xác minh được bằng ảnh",
  loi_he_thong: "Lỗi hệ thống khi phân tích",
};

function BieuTuongKetQua({ status }: { status: PhotoVerification["status"] }) {
  if (status === "khop") return <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />;
  if (status === "dang_xu_ly") return <Loader2 className="h-4 w-4 shrink-0 animate-spin" />;
  if (status === "khong_xac_minh_duoc" || status === "loi_he_thong")
    return <HelpCircle className="h-4 w-4 shrink-0 text-muted-foreground" />;
  return <XCircle className="h-4 w-4 shrink-0 text-destructive" />;
}

function MotLanChup({ v }: { v: PhotoVerification }) {
  const [loiAnh, setLoiAnh] = useState(false);
  return (
    <div className="space-y-2 rounded-xl border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-semibold">
          <BieuTuongKetQua status={v.status} /> Lần {v.attempt}/{v.maxAttempts} —{" "}
          {NHAN_KET_QUA[v.status] ?? v.status}
        </p>
        <span className="shrink-0 text-xs text-muted-foreground">
          {ngayHienThi(v.createdAt)} · {gioHienThi(v.createdAt)}
        </span>
      </div>

      {v.hasImage && !loiAnh ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={photoVerificationImageUrl(v.id)}
          alt={`Ảnh chụp lần ${v.attempt}`}
          className="max-h-64 w-full rounded-lg border border-border object-contain"
          onError={() => setLoiAnh(true)}
        />
      ) : (
        <div className="flex items-center gap-2 rounded-lg bg-muted p-3 text-xs text-muted-foreground">
          <ImageOff className="h-4 w-4 shrink-0" /> Ảnh không còn trên máy chủ.
        </div>
      )}

      {v.confidence && <p className="text-xs text-muted-foreground">Độ tin cậy: {v.confidence}</p>}
      <p className="text-sm">{v.message}</p>
    </div>
  );
}

export function DoseHistoryDialog({
  dose,
  open,
  onOpenChange,
}: {
  dose: Dose | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [danhSach, setDanhSach] = useState<PhotoVerification[]>([]);
  const [dangTai, setDangTai] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !dose) return;
    setDangTai(true);
    setLoi(null);
    listPhotoVerifications(dose.id)
      .then(setDanhSach)
      .catch((err) => setLoi(err instanceof Error ? err.message : "Không tải được lịch sử ảnh"))
      .finally(() => setDangTai(false));
  }, [open, dose]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{dose ? moTaThuoc(dose) : ""}</DialogTitle>
          <DialogDescription>
            {dose ? `${ngayHienThi(dose.scheduledAt)} · ${gioHienThi(dose.scheduledAt)}` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {dangTai && (
            <div className="flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Đang tải…
            </div>
          )}

          {loi && <p className="text-sm text-destructive">{loi}</p>}

          {!dangTai && !loi && danhSach.length === 0 && (
            <p className="p-3 text-center text-sm text-muted-foreground">
              Liều này chưa có lần chụp ảnh nào.
            </p>
          )}

          {danhSach.map((v) => (
            <MotLanChup key={v.id} v={v} />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
