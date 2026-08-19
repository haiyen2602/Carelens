"use client";

// Tab "Lịch sử" - port tu capyphone.js::renderHistory(), noi voi lich su
// lieu thuoc THAT.
//
// Ban mau hard-code "92%", "23/25 lieu", "🔥 7 ngay lien tiep" va 7 o mau
// co dinh. O day moi con so deu tinh tu `doses` that; bo phan "chuoi ngay
// lien tiep" vi chua co gi tinh duoc no. Dai pill "7 ngay/Hom nay/30 ngay"
// la bo loc that chu khong phai trang tri.

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { DoseHistoryDialog } from "@/components/dose-history-dialog";
import { CHIP, CHIP_THEO_TRANG_THAI, PillChip, SectionLabel } from "@/components/capy/capy-ui";
import { useAuth } from "@/lib/auth";
import { gioHienThi, listDoses, listPhotoVerifications, ngayHienThi, type Dose } from "@/lib/doses";

const KHOANG = [
  { key: "week", label: "7 ngày", days: 7 },
  { key: "today", label: "Hôm nay", days: 1 },
  { key: "month", label: "30 ngày", days: 30 },
] as const;
type KhoangKey = (typeof KHOANG)[number]["key"];

const TEN_THU = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

function khoaNgay(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

// So sanh theo NGAY-THANG cuc bo (khong phai epoch ms so voi "now"): mot
// lieu "hom nay 08:00 gio VN" luu UTC co the la moc UTC con o TUONG LAI so
// voi "now" ngay sau nua dem VN (UTC+7) du da duoc ghi TAKEN that trong
// ngay - so sanh epoch se loai nham lieu do khoi khoang.
function trongKhoang(iso: string, days: number): boolean {
  const d = new Date(iso);
  const nay = new Date();
  const dNgay = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const nayNgay = new Date(nay.getFullYear(), nay.getMonth(), nay.getDate()).getTime();
  const cach = Math.round((nayNgay - dNgay) / 86400000);
  return cach >= 0 && cach < days;
}

function tenThuoc(d: Dose): string {
  return d.expectedItems.map((i) => i.tenThuoc).join(", ") || "Thuốc";
}

export default function HistoryPage() {
  const { user } = useAuth();
  const patientId = user?.patient_id ?? "";
  // allDoses: TOAN BO lich - dung cho thong ke + bieu do 7 ngay. Khong the
  // dung `coAnh` (da loc chi con lieu co anh) vi lieu MISSED khong co anh
  // se bien mat khoi bieu do thay vi hien do.
  const [allDoses, setAllDoses] = useState<Dose[]>([]);
  const [coAnh, setCoAnh] = useState<Set<string>>(new Set());
  const [dangTai, setDangTai] = useState(true);
  const [dangXem, setDangXem] = useState<Dose | null>(null);
  const [khoang, setKhoang] = useState<KhoangKey>("week");

  useEffect(() => {
    if (!patientId) return;
    setDangTai(true);
    listDoses(patientId)
      .then(async (all) => {
        setAllDoses(all);
        const ketQua = await Promise.all(
          all.map(async (d) => {
            try {
              const lanChup = await listPhotoVerifications(d.id);
              return lanChup.some((v) => v.hasImage) ? d.id : null;
            } catch {
              return null;
            }
          }),
        );
        setCoAnh(new Set(ketQua.filter((id): id is string => id !== null)));
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : "Không tải được lịch sử"))
      .finally(() => setDangTai(false));
  }, [patientId]);

  const soNgay = KHOANG.find((k) => k.key === khoang)!.days;

  // Danh sach hien thi: cac lieu DA CHOT trong khoang (uong/tre/bo/huy) -
  // lieu PENDING chua toi gio khong thuoc "lich su".
  const danhSach = allDoses
    .filter(
      (d) =>
        trongKhoang(d.scheduledAt, soNgay) &&
        ["TAKEN", "DELAYED", "MISSED", "CANCELLED", "AWAITING_CAREGIVER"].includes(d.status),
    )
    .sort((a, b) => b.scheduledAt.localeCompare(a.scheduledAt));

  const tongKet = useMemo(() => {
    const trongKy = allDoses.filter((d) => trongKhoang(d.scheduledAt, soNgay));
    const daChot = trongKy.filter((d) => ["TAKEN", "DELAYED", "MISSED"].includes(d.status));
    const uong = daChot.filter((d) => d.status === "TAKEN" || d.status === "DELAYED").length;
    const muon = daChot.filter((d) => d.status === "DELAYED").length;
    const bo = daChot.filter((d) => d.status === "MISSED").length;
    return {
      coDuLieu: daChot.length > 0,
      pct: daChot.length > 0 ? Math.round((uong / daChot.length) * 100) : 0,
      uong,
      tong: daChot.length,
      muon,
      bo,
    };
  }, [allDoses, soNgay]);

  // 7 o = 7 ngay gan nhat, mau theo trang thai GOP cua ngay (khong phai cot
  // cao thap - dung dung cach cua ban thiet ke: 1 mau / 1 o).
  const bieuDo = useMemo(() => {
    const homNay = new Date();
    const o: { key: string; thu: string; mau: string; fg: string }[] = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(homNay);
      d.setDate(d.getDate() - i);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      const lieu = allDoses.filter((x) => khoaNgay(x.scheduledAt) === key);
      let mau = "#B7CBE8";
      let fg = "#2F5488";
      if (lieu.some((x) => x.status === "MISSED")) {
        mau = "#B4432C";
        fg = "#fff";
      } else if (lieu.some((x) => x.status === "DELAYED")) {
        mau = "#E39A16";
        fg = "#fff";
      } else if (lieu.length > 0 && lieu.every((x) => x.status === "TAKEN")) {
        mau = "#2E9E6B";
        fg = "#fff";
      }
      o.push({ key, thu: TEN_THU[d.getDay()], mau, fg });
    }
    return o;
  }, [allDoses]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display m-0 mt-1 text-[30px] font-extrabold leading-[1.1] text-[#16386E]">
        Lịch sử
      </h1>

      <div className="flex gap-2">
        {KHOANG.map((k) => (
          <button
            key={k.key}
            onClick={() => setKhoang(k.key)}
            className="rounded-full px-[15px] py-[9px] text-[13px] font-semibold transition-colors"
            style={
              khoang === k.key
                ? { background: "#16386E", color: "#fff" }
                : { background: "#fff", color: "#5B6A85" }
            }
          >
            {k.label}
          </button>
        ))}
      </div>

      {/* The tong ket */}
      {!dangTai && tongKet.coDuLieu && (
        <div className="rounded-[28px] bg-[#CFE6FF] p-5">
          <p className="font-display m-0 text-[40px] font-extrabold leading-none text-[#16386E]">
            {tongKet.pct}%
          </p>
          <p className="m-0 mt-1.5 text-[14px] font-semibold text-[#2F5488]">
            {tongKet.uong} / {tongKet.tong} liều đã hoàn thành
          </p>
          <p className="m-0 mt-0.5 text-[13px] text-[#3D5D8C]">
            {tongKet.muon} lần xác nhận muộn • {tongKet.bo} liều bỏ qua
          </p>
          <div className="mt-4 grid grid-cols-7 gap-1.5">
            {bieuDo.map((o) => (
              <span
                key={o.key}
                className="font-mono grid h-[52px] items-end justify-center rounded-[12px] pb-1 text-[9px] font-medium"
                style={{ background: o.mau, color: o.fg }}
              >
                {o.thu}
              </span>
            ))}
          </div>
        </div>
      )}

      {dangTai && (
        <div className="flex items-center justify-center gap-2 rounded-[24px] bg-white p-6 text-[13px] text-[#5B6A85]">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải lịch sử…
        </div>
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
                <p
                  className="truncate font-semibold"
                  title={`${ngayHienThi(d.scheduledAt)} · ${gioHienThi(d.scheduledAt)} · ${moTaThuoc(d)}`}
                >
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
