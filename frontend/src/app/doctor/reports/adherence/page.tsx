"use client";

import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Info,
  Lightbulb,
  Minus,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { HoverSelect } from "@/components/hover-select";
import { presentAlert } from "@/lib/alert-presentation";
import { useAuth } from "@/lib/auth";
import { getDoseSummary, type DoseSummary } from "@/lib/reporting";
import { useProto, type SysAlert } from "@/lib/proto-store";

const KHOANG_NGAY = [
  { value: "7", label: "7 ngày qua" },
  { value: "30", label: "30 ngày qua" },
  { value: "90", label: "90 ngày qua" },
];

// Duoi nguong nay thi hien SO DEM thay vi phan tram. "Bỏ lỡ 100%" cua 1 lieu
// doc nhu tham hoa nhung that ra chua noi len dieu gi - phan tram tren mau
// nho la cach nhanh nhat de mot bao cao noi doi ma khong ai phat hien.
const NGUONG_MAU_NHO = 10;

// Mau cho tung nhom, khop `key` do backend tra (xem _NHOM_TUAN_THU trong
// reporting_routes.py) - nguong chia nhom do backend giu, frontend chi to mau.
const MAU_NHOM: Record<string, string> = {
  good: "var(--success)",
  fair: "var(--primary)",
  poor: "var(--warning)",
  bad: "var(--destructive)",
  no_data: "var(--muted-foreground)",
};

const MAU_LOAI_CANH_BAO: Record<string, string> = {
  missed_dose: "bg-warning",
  safety_redflag: "bg-destructive",
  side_effect: "bg-primary",
  photo_mismatch: "bg-accent",
};

function formatPercent(value: number) {
  if (!Number.isFinite(value)) return "0";
  if (Number.isInteger(value)) return String(value);
  return (Math.trunc(value * 100) / 100).toFixed(2);
}

function tenThuVN(isoDate: string) {
  return ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][new Date(`${isoDate}T00:00:00`).getDay()];
}

function ngayNgan(isoDate: string) {
  const [, thang, ngay] = isoDate.split("-");
  return `${ngay}/${thang}`;
}

/** Mui ten so voi ky lien truoc. Tra null khi mot trong hai ky chua co du
 * lieu - "tang tu khong co gi" khong phai mot xu huong. */
function xuHuong(nay: number | null, truoc: number | null) {
  if (nay === null || truoc === null) return null;
  const chenh = nay - truoc;
  if (Math.abs(chenh) < 0.5) return { icon: Minus, tone: "text-muted-foreground", text: "không đổi" };
  return chenh > 0
    ? { icon: TrendingUp, tone: "text-success", text: `+${formatPercent(chenh)} điểm` }
    : { icon: TrendingDown, tone: "text-destructive", text: `${formatPercent(chenh)} điểm` };
}

export default function ReportAdherence() {
  const { alerts, prescriptions, patients } = useProto();
  const { accessToken } = useAuth();

  const [days, setDays] = useState("7");
  const [summary, setSummary] = useState<DoseSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loi, setLoi] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let huy = false;
    setLoading(true);
    getDoseSummary(accessToken, Number(days))
      .then((data) => {
        if (huy) return;
        setSummary(data);
        setLoi(null);
      })
      .catch((err: unknown) => {
        if (huy) return;
        setLoi(err instanceof Error ? err.message : "Không tải được thống kê.");
      })
      .finally(() => {
        if (!huy) setLoading(false);
      });
    return () => {
      huy = true;
    };
  }, [accessToken, days]);

  const soNgay = Number(days);
  const nhanKy = KHOANG_NGAY.find((k) => k.value === days)?.label ?? `${days} ngày qua`;

  // Canh bao van doc tu proto-store (khong co trong dose-summary) nhung PHAI
  // cat theo dung ky dang xem, neu khong lai lap lai dung loi cu: mot con so
  // toan thoi gian nam canh cac so lieu 7 ngay.
  const idTrongPhamVi = useMemo(
    () => new Set((summary?.patients ?? []).map((p) => p.patientId)),
    [summary],
  );
  const canhBaoTrongKy = useMemo(() => {
    const moc = Date.now() - soNgay * 86400000;
    return alerts.filter(
      (a) => idTrongPhamVi.has(a.patientId) && new Date(a.createdAt).getTime() >= moc,
    );
  }, [alerts, idTrongPhamVi, soNgay]);

  const openAlerts = canhBaoTrongKy.filter((a) => a.status === "new").length;

  // "Đơn thuốc đang chạy" truoc day la prescriptions.length - dem MOI phac do
  // o MOI trang thai (ke ca nhap/tu choi) cua MOI benh nhan, khong loc theo
  // pham vi dang theo doi nhu phan con lai cua trang.
  const donDangChay = useMemo(
    () =>
      prescriptions.filter((p) => p.status === "approved" && idTrongPhamVi.has(p.patientId)).length,
    [prescriptions, idTrongPhamVi],
  );

  const loaiCanhBao = useMemo(() => {
    const dem = new Map<string, { label: string; value: number }>();
    for (const a of canhBaoTrongKy) {
      const label = presentAlert(a, patients).triggerLabel;
      dem.set(a.trigger, { label, value: (dem.get(a.trigger)?.value ?? 0) + 1 });
    }
    return [...dem.entries()]
      .map(([trigger, v]) => ({ trigger, ...v }))
      .sort((a, b) => b.value - a.value);
  }, [canhBaoTrongKy, patients]);
  const alertMax = Math.max(1, ...loaiCanhBao.map((a) => a.value));

  const missedMax = Math.max(1, ...(summary?.missedByWindow ?? []).map((w) => w.missed));
  const tongBoLo = (summary?.missedByWindow ?? []).reduce((s, w) => s + w.missed, 0);
  const khungBoLoNhieuNhat =
    tongBoLo > 0 ? [...(summary?.missedByWindow ?? [])].sort((a, b) => b.missed - a.missed)[0] : null;

  // Gop cac ngay lien tiep khong co lieu thanh MOT dong - 6 dong "Không có
  // liều nào đến hạn" giong het nhau chiem het cho cua ngay thuc su co so lieu.
  const dongNgay = useMemo(() => {
    const ket: ({ loai: "ngay"; d: DoseSummary["daily"][number] } | { loai: "trong"; tu: string; den: string; so: number })[] = [];
    for (const d of summary?.daily ?? []) {
      if (d.total > 0) {
        ket.push({ loai: "ngay", d });
        continue;
      }
      const cuoi = ket[ket.length - 1];
      if (cuoi && cuoi.loai === "trong") {
        cuoi.den = d.date;
        cuoi.so += 1;
      } else {
        ket.push({ loai: "trong", tu: d.date, den: d.date, so: 1 });
      }
    }
    return ket;
  }, [summary]);

  const uuTien = useMemo(
    () => (summary?.patients ?? []).filter((p) => p.adherencePct !== null).slice(0, 4),
    [summary],
  );

  const tb = summary?.current.averageAdherencePct ?? null;
  const mauNho = (summary?.current.due ?? 0) > 0 && (summary?.current.due ?? 0) < NGUONG_MAU_NHO;
  const xh = xuHuong(tb, summary?.previous.averageAdherencePct ?? null);

  const stats = [
    {
      label: "Tuân thủ trung bình",
      value: tb === null ? "—" : `${formatPercent(tb)}%`,
      note:
        tb === null
          ? `Không có liều nào đến hạn trong ${nhanKy.toLowerCase()}`
          : `Trên ${summary?.current.taken}/${summary?.current.due} liều đã đến hạn`,
      trend: xh,
      icon: CheckCircle2,
      tone: "bg-success/15 text-success",
    },
    {
      label: "Bệnh nhân nguy cơ cao",
      value: summary?.highRiskCount ?? 0,
      note: `Tuân thủ dưới 75% · ${summary?.withDataCount ?? 0} BN có dữ liệu`,
      icon: Users,
      tone: "bg-destructive/12 text-destructive",
    },
    {
      label: "Cảnh báo mới",
      value: openAlerts,
      note: `Chưa xử lý · trong ${nhanKy.toLowerCase()}`,
      icon: AlertTriangle,
      tone: "bg-warning/25 text-warning-foreground",
    },
    {
      label: "Đơn thuốc đang chạy",
      value: donDangChay,
      note: "Đã duyệt, thuộc bệnh nhân đang theo dõi",
      icon: CalendarClock,
      tone: "bg-primary/10 text-primary",
    },
  ];

  const goiY: { title: string; detail: string }[] = [];
  if (mauNho) {
    goiY.push({
      title: "Mẫu còn nhỏ",
      detail: `Cả kỳ mới có ${summary?.current.due} liều đến hạn — tỉ lệ phần trăm chưa đủ căn cứ để kết luận. Cân nhắc mở rộng khoảng ngày.`,
    });
  }
  if ((summary?.highRiskCount ?? 0) > 0) {
    const idNguyCo = new Set(
      (summary?.patients ?? [])
        .filter((p) => p.adherencePct !== null && p.adherencePct < 75)
        .map((p) => p.patientId),
    );
    const coCanhBao = new Set(
      canhBaoTrongKy.filter((a) => a.status === "new" && idNguyCo.has(a.patientId)).map((a) => a.patientId),
    ).size;
    goiY.push({
      title: "Ưu tiên trong hôm nay",
      detail:
        coCanhBao > 0
          ? `${coCanhBao}/${summary?.highRiskCount} bệnh nhân tuân thủ dưới 75% đang có cảnh báo chưa xử lý — xem trước nhóm này.`
          : `${summary?.highRiskCount} bệnh nhân tuân thủ dưới 75%, hiện chưa ai có cảnh báo mới.`,
    });
  }
  if (khungBoLoNhieuNhat && khungBoLoNhieuNhat.missed > 0) {
    goiY.push({
      title: "Điều chỉnh nhắc nhở",
      detail: `Bỏ lỡ tập trung vào buổi ${khungBoLoNhieuNhat.label.toLowerCase()} (${khungBoLoNhieuNhat.missed}/${tongBoLo} lượt) — cân nhắc đổi giờ nhắc hoặc thêm người thân theo dõi.`,
    });
  }
  const nghiemTrong = canhBaoTrongKy.filter(
    (a: SysAlert) => a.level === "high" && a.status === "new",
  ).length;
  if (nghiemTrong > 0) {
    goiY.push({
      title: "Theo dõi an toàn",
      detail: `${nghiemTrong} cảnh báo mức nghiêm trọng chưa xử lý — nên xem trước các cảnh báo hành chính.`,
    });
  }

  const boChonNgay = (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground">Khoảng thống kê</span>
      <div className="w-44">
        <HoverSelect value={days} onChange={setDays} options={KHOANG_NGAY} />
      </div>
    </div>
  );

  if (summary && summary.patientCount === 0) {
    return (
      <div className="space-y-5">
        <header className="flex justify-end">{boChonNgay}</header>
        <div className="surface-card p-10 text-center">
          <Users className="mx-auto h-10 w-10 text-muted-foreground/40" />
          <p className="mt-3 font-semibold">Chưa có bệnh nhân nào để thống kê</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Trang này tổng hợp trên các bệnh nhân bạn đang theo dõi. Bấm{" "}
            <span className="font-semibold text-foreground">Theo dõi</span> ở trang{" "}
            <Link href="/doctor/patients" className="font-semibold text-primary">
              Quản lý bệnh nhân
            </Link>{" "}
            để bắt đầu.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {summary ? (
            <>
              Số liệu từ <span className="font-semibold text-foreground">{ngayNgan(summary.fromDate)}</span>{" "}
              đến <span className="font-semibold text-foreground">{ngayNgan(summary.toDate)}</span> ·{" "}
              {summary.patientCount} bệnh nhân đang theo dõi
            </>
          ) : (
            "Đang tải…"
          )}
        </p>
        {boChonNgay}
      </header>

      {loi && <div className="surface-card p-6 text-sm text-destructive">{loi}</div>}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          const Trend = s.trend?.icon;
          return (
            <div key={s.label} className={`surface-card flex items-start gap-4 p-5 ${loading ? "opacity-60" : ""}`}>
              <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-2xl ${s.tone}`}>
                <Icon className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <p className="text-sm text-muted-foreground">{s.label}</p>
                <div className="mt-1 flex flex-wrap items-baseline gap-2">
                  <p className="text-3xl font-extrabold leading-none">{s.value}</p>
                  {Trend && s.trend && (
                    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${s.trend.tone}`}>
                      <Trend className="h-3.5 w-3.5" />
                      {s.trend.text}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">{s.note}</p>
              </div>
            </div>
          );
        })}
      </section>

      {mauNho && (
        <div className="flex gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning-foreground" />
          <p>
            <span className="font-semibold">Mẫu nhỏ: </span>
            cả kỳ chỉ có {summary?.current.due} liều đến hạn. Các tỉ lệ phần trăm bên dưới dễ gây
            hiểu nhầm — nên đọc theo số lượt thay vì phần trăm.
          </p>
        </div>
      )}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Phân bố mức tuân thủ</h2>
          <p className="text-sm text-muted-foreground">
            {summary?.patientCount ?? 0} bệnh nhân đang theo dõi, tính theo {nhanKy.toLowerCase()}.
          </p>

          {summary && (
            <>
              {/* Thanh gop 100%: thay ngay co cau, khong phai doc 5 dong roi tu
                  cong nham. Truoc day moi thanh chuan hoa theo nhom LON NHAT
                  nen nhom dong nhat luon dai het khung du chi chiem 5%. */}
              <div className="mt-5 flex h-4 overflow-hidden rounded-full bg-muted">
                {summary.buckets
                  .filter((b) => b.count > 0)
                  .map((b) => (
                    <div
                      key={b.key}
                      title={`${b.label}: ${b.count} BN`}
                      style={{
                        width: `${(b.count / Math.max(1, summary.patientCount)) * 100}%`,
                        background: MAU_NHOM[b.key],
                      }}
                    />
                  ))}
              </div>

              <ul className="mt-5 space-y-2.5">
                {summary.buckets.map((b) => {
                  const pct = (b.count / Math.max(1, summary.patientCount)) * 100;
                  return (
                    <li
                      key={b.key}
                      className={`flex items-center gap-3 text-sm ${b.count === 0 ? "opacity-45" : ""}`}
                    >
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ background: MAU_NHOM[b.key] }}
                      />
                      <span className="min-w-0 flex-1 truncate font-medium">{b.label}</span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">
                        {b.count} BN
                      </span>
                      <span className="w-12 shrink-0 text-right font-semibold tabular-nums">
                        {Math.round(pct)}%
                      </span>
                    </li>
                  );
                })}
              </ul>

              {summary.withoutDataCount > 0 && (
                <p className="mt-4 text-xs text-muted-foreground">
                  “Chưa có dữ liệu” là bệnh nhân không có liều nào đến hạn trong kỳ — không phải
                  tuân thủ 0%.
                </p>
              )}
            </>
          )}
        </div>

        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Tình trạng liều theo ngày</h2>
          <p className="text-sm text-muted-foreground">Tỷ lệ dùng đúng, trễ và bỏ lỡ theo ngày.</p>

          {loading && !summary && <p className="mt-6 text-sm text-muted-foreground">Đang tải…</p>}
          {summary && (
            <div className="mt-5 space-y-3">
              {dongNgay.map((row) =>
                row.loai === "trong" ? (
                  <p
                    key={`trong-${row.tu}`}
                    className="rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
                  >
                    {row.so === 1
                      ? `${tenThuVN(row.tu)} ${ngayNgan(row.tu)} — không có liều nào đến hạn`
                      : `${row.so} ngày không có liều nào đến hạn (${ngayNgan(row.tu)}–${ngayNgan(row.den)})`}
                  </p>
                ) : (
                  <div
                    key={row.d.date}
                    className="grid grid-cols-[64px_minmax(0,1fr)] items-center gap-3"
                  >
                    <p className="text-sm font-bold text-muted-foreground">
                      {tenThuVN(row.d.date)}
                      <span className="ml-1 text-xs font-normal">{ngayNgan(row.d.date)}</span>
                    </p>
                    <div>
                      <div className="flex h-3 overflow-hidden rounded-full bg-muted">
                        <div
                          className="bg-success"
                          style={{ width: `${(row.d.taken / row.d.total) * 100}%` }}
                        />
                        <div
                          className="bg-warning"
                          style={{ width: `${(row.d.delayed / row.d.total) * 100}%` }}
                        />
                        <div
                          className="bg-destructive"
                          style={{ width: `${(row.d.missed / row.d.total) * 100}%` }}
                        />
                      </div>
                      {/* Mau nho thi noi bang SO LUOT, khong bang phan tram -
                          "bỏ lỡ 100%" cua 1 lieu doc nhu tham hoa. */}
                      <p className="mt-1 text-xs text-muted-foreground">
                        {row.d.total < NGUONG_MAU_NHO
                          ? `Đúng ${row.d.taken} · Trễ ${row.d.delayed} · Bỏ lỡ ${row.d.missed} (${row.d.total} liều)`
                          : `Đúng ${Math.round((row.d.taken / row.d.total) * 100)}% · Trễ ${Math.round((row.d.delayed / row.d.total) * 100)}% · Bỏ lỡ ${Math.round((row.d.missed / row.d.total) * 100)}% (${row.d.total} liều)`}
                      </p>
                    </div>
                  </div>
                ),
              )}
            </div>
          )}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-3">
        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Cảnh báo theo loại</h2>
          <p className="text-sm text-muted-foreground">Cảnh báo phát sinh trong {nhanKy.toLowerCase()}.</p>
          {loaiCanhBao.length === 0 ? (
            <p className="mt-6 text-sm text-muted-foreground">Không có cảnh báo nào trong kỳ.</p>
          ) : (
            <div className="mt-5 space-y-4">
              {loaiCanhBao.map((a) => (
                <div key={a.trigger}>
                  <div className="mb-1 flex items-center justify-between gap-3 text-sm">
                    <span className="min-w-0 truncate font-semibold">{a.label}</span>
                    <span className="shrink-0 text-muted-foreground">{a.value}</span>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className={`h-full rounded-full ${MAU_LOAI_CANH_BAO[a.trigger] ?? "bg-muted-foreground/40"}`}
                      style={{ width: `${(a.value / alertMax) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Khung giờ hay bỏ lỡ</h2>
          <p className="text-sm text-muted-foreground">Giúp bác sĩ điều chỉnh nhắc nhở khi cần.</p>
          {loading && !summary && <p className="mt-6 text-sm text-muted-foreground">Đang tải…</p>}
          {summary && tongBoLo === 0 && (
            <p className="mt-6 text-sm text-muted-foreground">
              Không có liều nào bị bỏ lỡ trong kỳ.
            </p>
          )}
          {summary && tongBoLo > 0 && (
            <div className="mt-5 flex h-48 items-end gap-4">
              {summary.missedByWindow.map((w) => (
                <div key={w.key} className="flex min-w-0 flex-1 flex-col items-center gap-2">
                  <div className="flex h-36 w-full items-end rounded-lg bg-muted/60 px-2">
                    <div
                      className="w-full rounded-t-md bg-primary transition-[height]"
                      style={{ height: `${(w.missed / missedMax) * 100}%` }}
                    />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-bold">{w.missed}</p>
                    <p className="text-xs text-muted-foreground">{w.label}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Bệnh nhân cần ưu tiên</h2>
          <p className="text-sm text-muted-foreground">Xếp theo tỷ lệ tuân thủ thấp nhất.</p>
          {uuTien.length === 0 ? (
            <p className="mt-6 text-sm text-muted-foreground">
              Chưa bệnh nhân nào có liều đến hạn trong kỳ để xếp hạng.
            </p>
          ) : (
            <div className="mt-5 space-y-3">
              {uuTien.map((p) => {
                const pct = p.adherencePct ?? 0;
                const mau =
                  pct >= 90 ? MAU_NHOM.good : pct >= 70 ? MAU_NHOM.fair : pct >= 50 ? MAU_NHOM.poor : MAU_NHOM.bad;
                return (
                  <div key={p.patientId} className="rounded-lg border border-border p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-bold" title={p.fullName}>
                          {p.fullName}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {p.note || "Chưa có ghi chú"}
                        </p>
                      </div>
                      <span className="shrink-0 whitespace-nowrap rounded-md bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground">
                        {p.taken}/{p.due} liều
                      </span>
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${pct}%`, background: mau }}
                        />
                      </div>
                      <p className="w-14 text-right text-xs font-semibold tabular-nums">
                        {formatPercent(pct)}%
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {goiY.length > 0 && (
        <section className="surface-card p-6">
          <div className="flex items-center gap-2">
            <Clock3 className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-bold">Gợi ý đọc nhanh cho bác sĩ</h2>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {goiY.map((g) => (
              <div key={g.title} className="rounded-lg bg-muted/45 p-4">
                <p className="flex items-center gap-1.5 text-sm font-bold">
                  <Lightbulb className="h-4 w-4 shrink-0 text-primary" />
                  {g.title}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">{g.detail}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
