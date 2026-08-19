"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Check, ImageOff, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { listMonitoredPatients, type MonitoredPatient } from "@/lib/caregivers";
import {
  gioHienThi,
  listDoses,
  listPhotoVerifications,
  moTaThuoc,
  ngayHienThi,
  photoVerificationImageUrl,
  updateDoseStatus,
  type Dose,
  type PhotoVerification,
} from "@/lib/doses";

const toneTheoMuc: Record<string, string> = {
  LOW: "bg-secondary text-secondary-foreground",
  MEDIUM: "bg-warning/25 text-warning-foreground",
  HIGH: "bg-destructive/15 text-destructive",
};

function NgayGio({ iso }: { iso: string }) {
  return (
    <span>
      {ngayHienThi(iso)} · {gioHienThi(iso)}
    </span>
  );
}

function AnhCanDuyet({ dose, onXong }: { dose: Dose; onXong: () => void }) {
  const { accessToken } = useAuth();
  const [lanChup, setLanChup] = useState<PhotoVerification[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const [dangXuLy, setDangXuLy] = useState(false);

  useEffect(() => {
    listPhotoVerifications(dose.id)
      .then(setLanChup)
      .catch(() => setLanChup([]))
      .finally(() => setDangTai(false));
  }, [dose.id]);

  const xacNhan = async (trangThai: "TAKEN" | "MISSED") => {
    setDangXuLy(true);
    try {
      await updateDoseStatus(dose.id, trangThai, accessToken);
      toast.success(trangThai === "TAKEN" ? "Đã xác nhận: đã uống" : "Đã xác nhận: bỏ liều");
      onXong();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không xác nhận được");
    } finally {
      setDangXuLy(false);
    }
  };

  const lanCuoi = lanChup[lanChup.length - 1];

  return (
    <div className="surface-card space-y-3 p-4">
      <div>
        <p className="font-semibold">
          <NgayGio iso={dose.scheduledAt} /> · {moTaThuoc(dose)}
        </p>
        <p className="text-xs text-muted-foreground">
          {dangTai
            ? "Đang kiểm tra ảnh xác nhận…"
            : lanCuoi
              ? `Đã chụp ${lanChup.length} lần, ảnh vẫn không khớp đơn thuốc — cần bạn xem giúp.`
              : "Bệnh nhân báo đã uống nhưng chưa gửi ảnh xác nhận — bạn xem giúp nhé."}
        </p>
      </div>

      {dangTai && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải ảnh…
        </div>
      )}

      {!dangTai && lanCuoi && (
        <div className="space-y-2">
          {lanCuoi.hasImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={photoVerificationImageUrl(lanCuoi.id)}
              alt={`Ảnh chụp lần ${lanCuoi.attempt}`}
              className="max-h-64 w-full rounded-lg border border-border object-contain"
            />
          ) : (
            <div className="flex items-center gap-2 rounded-lg bg-muted p-3 text-xs text-muted-foreground">
              <ImageOff className="h-4 w-4 shrink-0" /> Ảnh không còn trên máy chủ.
            </div>
          )}
          <p className="text-sm">{lanCuoi.message}</p>
        </div>
      )}

      <div className="flex gap-2">
        <Button className="flex-1" disabled={dangXuLy} onClick={() => xacNhan("TAKEN")}>
          <Check className="mr-1 h-4 w-4" /> Xác nhận đã uống
        </Button>
        <Button
          variant="outline"
          className="flex-1 text-destructive"
          disabled={dangXuLy}
          onClick={() => xacNhan("MISSED")}
        >
          <X className="mr-1 h-4 w-4" /> Xác nhận bỏ liều
        </Button>
      </div>
    </div>
  );
}

export default function MonitoredRelativeDetailPage() {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const [relative, setRelative] = useState<MonitoredPatient | null>(null);
  const [dosesCanDuyet, setDosesCanDuyet] = useState<Dose[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const [tab, setTab] = useState<"canh_bao" | "duyet">("canh_bao");

  const taiLai = async () => {
    if (!user?.id) return;
    setDangTai(true);
    try {
      const [ds, doses] = await Promise.all([
        listMonitoredPatients(user.id),
        listDoses(params.id).catch(() => [] as Dose[]),
      ]);
      setRelative(ds.find((r) => r.patientId === params.id) ?? null);
      setDosesCanDuyet(doses.filter((d) => d.status === "AWAITING_CAREGIVER"));
    } finally {
      setDangTai(false);
    }
  };

  useEffect(() => {
    taiLai();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, params.id]);

  if (dangTai) {
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Đang tải…
      </div>
    );
  }

  if (!relative) {
    return (
      <div className="space-y-4">
        <Link href="/patient/family" className="flex items-center gap-1.5 text-sm text-primary">
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </Link>
        <p className="surface-card p-6 text-center text-sm text-muted-foreground">
          Không tìm thấy người thân này — có thể bạn chưa được họ đồng ý theo dõi.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Link href="/patient/family" className="flex items-center gap-1.5 text-sm text-primary">
        <ArrowLeft className="h-4 w-4" /> Quay lại
      </Link>

      <section className="surface-card p-5">
        <div className="flex items-center gap-3">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent text-lg font-bold text-accent-foreground">
            {relative.fullName.charAt(0)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-bold">{relative.fullName}</p>
            <p className="truncate text-sm text-muted-foreground">
              {relative.relationship}
              {relative.yearOfBirth
                ? ` · ${new Date().getFullYear() - relative.yearOfBirth} tuổi`
                : ""}
            </p>
          </div>
          {relative.adherencePct !== null && (
            <span className="shrink-0 text-xl font-extrabold text-primary">
              {Math.round(relative.adherencePct)}%
            </span>
          )}
        </div>
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Đã uống {relative.doseTakenToday}/{relative.doseTotalToday} liều hôm nay
        </p>
      </section>

      <div className="grid grid-cols-2 gap-2 rounded-xl bg-muted p-1">
        <button
          onClick={() => setTab("canh_bao")}
          className={`rounded-lg py-2 text-sm font-semibold transition-colors ${
            tab === "canh_bao" ? "bg-card shadow-sm" : "text-muted-foreground"
          }`}
        >
          Cảnh báo {relative.openEscalations.length > 0 && `(${relative.openEscalations.length})`}
        </button>
        <button
          onClick={() => setTab("duyet")}
          className={`rounded-lg py-2 text-sm font-semibold transition-colors ${
            tab === "duyet" ? "bg-card shadow-sm" : "text-muted-foreground"
          }`}
        >
          Duyệt uống thuốc {dosesCanDuyet.length > 0 && `(${dosesCanDuyet.length})`}
        </button>
      </div>

      {tab === "canh_bao" && (
        <section className="space-y-2">
          {relative.openEscalations.length === 0 && (
            <p className="surface-card p-6 text-center text-sm text-muted-foreground">
              Không có cảnh báo nào đang mở.
            </p>
          )}
          {relative.openEscalations.map((a) => (
            <div key={a.id} className="surface-card flex items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{a.title}</p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${
                  toneTheoMuc[a.level] ?? "bg-secondary text-secondary-foreground"
                }`}
              >
                <NgayGio iso={a.createdAt} />
              </span>
            </div>
          ))}
        </section>
      )}

      {tab === "duyet" && (
        <section className="space-y-3">
          {dosesCanDuyet.length === 0 && (
            <p className="surface-card p-6 text-center text-sm text-muted-foreground">
              Không có liều nào cần bạn duyệt.
            </p>
          )}
          {dosesCanDuyet.map((d) => (
            <AnhCanDuyet key={d.id} dose={d} onXong={taiLai} />
          ))}
        </section>
      )}
    </div>
  );
}
