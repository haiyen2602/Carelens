"use client";

import { useEffect, useMemo, useState } from "react";
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

const KHOANG_NGAY = [
  { key: "today", label: "Hôm nay", days: 1 },
  { key: "week", label: "7 ngày", days: 7 },
  { key: "month", label: "30 ngày", days: 30 },
] as const;
type KhoangKey = (typeof KHOANG_NGAY)[number]["key"];

const TEN_THU = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

function ngayCucBo(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

// So sanh theo NGAY-THANG cuc bo (khong phai epoch ms so voi "now") - giong
// cach laHomNay() o patient/page.tsx dang lam. Bat buoc phai vay: mot lieu
// "hom nay 08:00 gio VN" luu UTC co the la mot moc UTC con o TUONG LAI so
// voi "now" ngay khi vua qua nua dem VN (VN = UTC+7), du no da duoc ghi
// TAKEN that trong ngay hom nay - so sanh epoch se loai nham lieu do khoi
// khoang "hom nay/7 ngay/30 ngay".
function trongKhoang(iso: string, days: number): boolean {
  const d = new Date(iso);
  const nay = new Date();
  const dNgay = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const nayNgay = new Date(nay.getFullYear(), nay.getMonth(), nay.getDate()).getTime();
  const soNgayCach = Math.round((nayNgay - dNgay) / (24 * 60 * 60 * 1000));
  return soNgayCach >= 0 && soNgayCach < days;
}

export default function HistoryPage() {
  const { user } = useAuth();
  const patientId = user?.patient_id ?? "";
  // allDoses: TOAN BO lich (ke ca chua chup anh/bo lo) - dung cho thong ke +
  // bieu do 7 ngay, khong the dung `doses` (da loc chi con lieu co anh) vi
  // lieu MISSED khong co anh se bien mat khoi bieu do thay vi hien do.
  const [allDoses, setAllDoses] = useState<Dose[]>([]);
  const [doses, setDoses] = useState<Dose[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const [dangXem, setDangXem] = useState<Dose | null>(null);
  const [khoang, setKhoang] = useState<KhoangKey>("week");

  useEffect(() => {
    if (!patientId) return;
    setDangTai(true);
    listDoses(patientId)
      .then(async (all) => {
        setAllDoses(all);
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

  const soNgay = KHOANG_NGAY.find((k) => k.key === khoang)!.days;
  const daSapXep = [...doses]
    .filter((d) => trongKhoang(d.scheduledAt, soNgay))
    .sort((a, b) => b.scheduledAt.localeCompare(a.scheduledAt));

  const tongKet = useMemo(() => {
    const trongKy = allDoses.filter((d) => trongKhoang(d.scheduledAt, soNgay));
    const daUong = trongKy.filter((d) => d.status === "TAKEN" || d.status === "DELAYED").length;
    const muon = trongKy.filter((d) => d.status === "DELAYED").length;
    const boQua = trongKy.filter((d) => d.status === "MISSED").length;
    const daXongHan = trongKy.filter((d) =>
      ["TAKEN", "DELAYED", "MISSED"].includes(d.status),
    ).length;
    const phanTram = daXongHan > 0 ? Math.round((daUong / daXongHan) * 100) : null;
    return { tong: trongKy.length, daUong, muon, boQua, phanTram };
  }, [allDoses, soNgay]);

  // Bieu do 7 ngay gan nhat (thu-day chip, mau theo trang thai gop cua ngay
  // do - khong phai bar cao thap, dung cach cua ban thiet ke: 1 mau/1 o).
  const bieuDo7Ngay = useMemo(() => {
    const homNay = new Date();
    const oNgay: { key: string; thu: string; mau: string; chuToi: boolean }[] = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(homNay);
      d.setDate(d.getDate() - i);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      const lieuTrongNgay = allDoses.filter((dose) => ngayCucBo(dose.scheduledAt) === key);
      let mau = "bg-secondary"; // chua co du lieu / tuong lai
      let chuToi = false;
      if (lieuTrongNgay.length > 0) {
        if (lieuTrongNgay.some((dd) => dd.status === "MISSED")) {
          mau = "bg-destructive";
          chuToi = true;
        } else if (lieuTrongNgay.some((dd) => dd.status === "DELAYED")) {
          mau = "bg-warning";
          chuToi = true;
        } else if (lieuTrongNgay.every((dd) => dd.status === "TAKEN")) {
          mau = "bg-success";
          chuToi = true;
        }
      }
      oNgay.push({ key, thu: TEN_THU[d.getDay()], mau, chuToi });
    }
    return oNgay;
  }, [allDoses]);

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl font-extrabold">Lịch sử</h1>

      <div className="flex gap-2">
        {KHOANG_NGAY.map((k) => (
          <button
            key={k.key}
            onClick={() => setKhoang(k.key)}
            className={`rounded-full px-3.5 py-2 text-[13px] font-semibold ${
              khoang === k.key
                ? "bg-primary text-primary-foreground"
                : "bg-card text-muted-foreground"
            }`}
          >
            {k.label}
          </button>
        ))}
      </div>

      {!dangTai && tongKet.tong > 0 && (
        <section className="rounded-[28px] p-5" style={{ backgroundColor: "var(--capy-sky)" }}>
          {tongKet.phanTram !== null && (
            <p className="font-display text-4xl font-extrabold text-primary">{tongKet.phanTram}%</p>
          )}
          <p className="mt-1 text-sm font-semibold text-primary/80">
            {tongKet.daUong} / {tongKet.tong} liều đã hoàn thành
          </p>
          <p className="font-mono mt-1 text-xs text-primary/70">
            {tongKet.muon} lần xác nhận muộn · {tongKet.boQua} liều bỏ qua
          </p>

          <div className="mt-4 grid grid-cols-7 gap-1.5">
            {bieuDo7Ngay.map((o) => (
              <div
                key={o.key}
                className={`grid h-[52px] items-end justify-center rounded-xl pb-1 ${o.mau} ${
                  o.chuToi ? "text-white" : "text-primary/70"
                }`}
              >
                <span className="font-mono text-[9px] font-medium">{o.thu}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {dangTai && (
        <div className="flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải lịch sử…
        </div>
      )}

      {!dangTai && daSapXep.length === 0 && (
        <p className="surface-card p-6 text-center text-sm text-muted-foreground">
          Chưa có liều thuốc nào trong khoảng này.
        </p>
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
                  {ngayHienThi(d.scheduledAt)} ·{" "}
                  <span className="font-mono">{gioHienThi(d.scheduledAt)}</span> · {moTaThuoc(d)}
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
