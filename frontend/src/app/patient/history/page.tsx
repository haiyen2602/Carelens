"use client";

import { useEffect, useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import {
  gioHienThi,
  listDoses,
  listPhotoVerifications,
  moTaThuoc,
  ngayHienThi,
  NHAN_TRANG_THAI_LIEU,
  type Dose,
} from "@/lib/doses";
import { DoseHistoryDialog } from "@/components/dose-history-dialog";

const MAU_THEO_TRANG_THAI: Record<string, string> = {
  TAKEN: "bg-success/15 text-success",
  DELAYED: "bg-success/15 text-success",
  MISSED: "bg-destructive/15 text-destructive",
  AWAITING_CAREGIVER: "bg-warning/25 text-warning-foreground",
  CANCELLED: "bg-muted text-muted-foreground",
  PENDING: "bg-secondary text-secondary-foreground",
};

export default function HistoryPage() {
  const { user } = useAuth();
  const patientId = user?.patient_id ?? "";
  const [doses, setDoses] = useState<Dose[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const [dangXem, setDangXem] = useState<Dose | null>(null);

  useEffect(() => {
    if (!patientId) return;
    setDangTai(true);
    listDoses(patientId)
      .then(async (all) => {
        // Chi giu lieu THAT SU da co anh chup - "Cho xac nhan" (PENDING, chua
        // chup) hoac bi huy/bo lo ma khong chup lan nao deu khong thuoc
        // "lich su" theo yeu cau, du trang thai co the khac nhau.
        const coAnh = await Promise.all(
          all.map(async (d) => {
            try {
              const lanChup = await listPhotoVerifications(d.id);
              return lanChup.some((v) => v.hasImage) ? d : null;
            } catch {
              return null;
            }
          }),
        );
        setDoses(coAnh.filter((d): d is Dose => d !== null));
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : "Không tải được lịch sử"))
      .finally(() => setDangTai(false));
  }, [patientId]);

  const daSapXep = [...doses].sort((a, b) => b.scheduledAt.localeCompare(a.scheduledAt));

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold">Lịch sử</h1>

      {dangTai && (
        <div className="flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải lịch sử…
        </div>
      )}

      {!dangTai && daSapXep.length === 0 && (
        <p className="p-6 text-center text-sm text-muted-foreground">Chưa có liều thuốc nào.</p>
      )}

      {!dangTai && daSapXep.length > 0 && (
        <section className="surface-card divide-y divide-border">
          {daSapXep.map((d) => (
            <button
              key={d.id}
              onClick={() => setDangXem(d)}
              className="grid w-full grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 p-4 text-left hover:bg-muted/50"
            >
              <div className="min-w-0">
                <p className="truncate font-semibold">
                  {ngayHienThi(d.scheduledAt)} · {gioHienThi(d.scheduledAt)} · {moTaThuoc(d)}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${
                  MAU_THEO_TRANG_THAI[d.status] ?? "bg-secondary text-secondary-foreground"
                }`}
              >
                {NHAN_TRANG_THAI_LIEU[d.status] ?? d.status}
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          ))}
        </section>
      )}

      <DoseHistoryDialog
        dose={dangXem}
        open={dangXem !== null}
        onOpenChange={(o) => {
          if (!o) setDangXem(null);
        }}
      />
    </div>
  );
}
