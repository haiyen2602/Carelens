"use client";

import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Lightbulb,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { presentAlert } from "@/lib/alert-presentation";
import { useAuth } from "@/lib/auth";
import { getDoseSummary, type DoseSummary } from "@/lib/reporting";
import { useProto, type Patient, type SysAlert } from "@/lib/proto-store";

const SO_NGAY = 7;

// Nguong chia nhom tuan thu. Dung CHUNG mot bang cho ca bieu do phan bo lan
// nhan "Rat kem/Kem/..." o danh sach uu tien - truoc day hai cho dinh nghia
// rieng nen co the noi khac nhau ve cung mot benh nhan.
const NHOM_TUAN_THU = [
  { key: "good", label: "Tuân thủ tốt", range: ">= 90%", color: "var(--success)", min: 90 },
  { key: "fair", label: "Trung bình", range: "70-89%", color: "var(--primary)", min: 70 },
  { key: "poor", label: "Kém", range: "50-69%", color: "var(--warning)", min: 50 },
  { key: "bad", label: "Rất kém", range: "< 50%", color: "var(--destructive)", min: 0 },
] as const;

// Mau cho tung loai canh bao, khop voi `trigger` cua Escalation. Nhan tieng
// Viet lay tu presentAlert() chu khong viet lai o day - mot ban dich duy nhat
// cho ca app (xem lib/alert-presentation.ts).
const MAU_LOAI_CANH_BAO: Record<string, string> = {
  missed_dose: "bg-warning",
  safety_redflag: "bg-destructive",
  side_effect: "bg-primary",
  photo_mismatch: "bg-accent",
};

function nhomCua(adherence: number) {
  return NHOM_TUAN_THU.find((n) => adherence >= n.min) ?? NHOM_TUAN_THU[NHOM_TUAN_THU.length - 1];
}

function formatPercent(value: number) {
  if (!Number.isFinite(value)) return "0";
  if (Number.isInteger(value)) return String(value);
  return (Math.trunc(value * 100) / 100).toFixed(2);
}

function tenThuVN(isoDate: string) {
  const d = new Date(`${isoDate}T00:00:00`);
  return ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][d.getDay()];
}

function ngayNgan(isoDate: string) {
  const [, thang, ngay] = isoDate.split("-");
  return `${ngay}/${thang}`;
}

export default function ReportAdherence() {
  const { patients, alerts, prescriptions } = useProto();
  const { accessToken } = useAuth();

  const [summary, setSummary] = useState<DoseSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loiSummary, setLoiSummary] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let huy = false;
    setLoadingSummary(true);
    getDoseSummary(accessToken, SO_NGAY)
      .then((data) => {
        if (huy) return;
        setSummary(data);
        setLoiSummary(null);
      })
      .catch((err: unknown) => {
        if (huy) return;
        setLoiSummary(err instanceof Error ? err.message : "Không tải được thống kê liều.");
      })
      .finally(() => {
        if (!huy) setLoadingSummary(false);
      });
    return () => {
      huy = true;
    };
  }, [accessToken]);

  // Pham vi: CHI benh nhan dang "Theo doi" - khop voi chu thich tren the va
  // voi Hop canh bao (cung chi hien benh nhan dang theo doi). `/reporting/
  // patients` tra ve toan bo benh nhan trong he thong nen phai loc o day.
  const theoDoi = useMemo(() => patients.filter((p) => p.watch), [patients]);

  // Benh nhan chua co lieu nao den han (adherence === null) bi loai khoi MOI
  // phep tinh ty le - dua vao mau se lam sai lech, dung y do cua backend khi
  // tra null thay vi 0 (xem services/reporting/adherence.py).
  const coSoLieu = useMemo(
    () => theoDoi.filter((p): p is Patient & { adherence: number } => p.adherence !== null),
    [theoDoi],
  );
  const chuaCoSoLieu = theoDoi.length - coSoLieu.length;

  const avg =
    coSoLieu.length > 0
      ? coSoLieu.reduce((s, p) => s + p.adherence, 0) / coSoLieu.length
      : null;
  const highRisk = coSoLieu.filter((p) => p.adherence < 75);

  const idTheoDoi = useMemo(() => new Set(theoDoi.map((p) => p.id)), [theoDoi]);
  const canhBaoTrongPhamVi = useMemo(
    () => alerts.filter((a) => idTheoDoi.has(a.patientId)),
    [alerts, idTheoDoi],
  );
  const openAlerts = canhBaoTrongPhamVi.filter((a) => a.status === "new").length;

  const nhomTuanThu = useMemo(
    () =>
      NHOM_TUAN_THU.map((n) => ({
        ...n,
        value: coSoLieu.filter((p) => nhomCua(p.adherence).key === n.key).length,
      })),
    [coSoLieu],
  );
  const bucketMax = Math.max(1, ...nhomTuanThu.map((b) => b.value));

  // Canh bao theo loai trong SO_NGAY ngay gan nhat - cung khung thoi gian voi
  // bieu do lieu ben canh de hai so lieu doc chung mot cau chuyen.
  const loaiCanhBao = useMemo(() => {
    const moc = Date.now() - SO_NGAY * 86400000;
    const dem = new Map<string, { label: string; value: number }>();
    for (const a of canhBaoTrongPhamVi) {
      if (new Date(a.createdAt).getTime() < moc) continue;
      const label = presentAlert(a, patients).triggerLabel;
      const cu = dem.get(a.trigger);
      dem.set(a.trigger, { label, value: (cu?.value ?? 0) + 1 });
    }
    return [...dem.entries()]
      .map(([trigger, v]) => ({ trigger, ...v }))
      .sort((a, b) => b.value - a.value);
  }, [canhBaoTrongPhamVi, patients]);
  const alertMax = Math.max(1, ...loaiCanhBao.map((a) => a.value));

  const missedMax = Math.max(1, ...(summary?.missedByWindow ?? []).map((w) => w.missed));
  const tongBoLo = (summary?.missedByWindow ?? []).reduce((s, w) => s + w.missed, 0);
  const khungBoLoNhieuNhat =
    tongBoLo > 0
      ? [...(summary?.missedByWindow ?? [])].sort((a, b) => b.missed - a.missed)[0]
      : null;

  const uuTien = useMemo(
    () => [...coSoLieu].sort((a, b) => a.adherence - b.adherence).slice(0, 4),
    [coSoLieu],
  );

  const stats = [
    {
      label: "Tuân thủ trung bình",
      value: avg === null ? "—" : `${formatPercent(avg)}%`,
      note:
        avg === null
          ? "Chưa bệnh nhân nào có liều đến hạn"
          : chuaCoSoLieu > 0
            ? `Trên ${coSoLieu.length} BN có dữ liệu · ${chuaCoSoLieu} BN chưa tính được`
            : `Trên ${coSoLieu.length} bệnh nhân đang theo dõi`,
      icon: CheckCircle2,
      tone: "bg-success/15 text-success",
    },
    {
      label: "Bệnh nhân nguy cơ cao",
      value: highRisk.length,
      note: "Tuân thủ dưới 75%",
      icon: Users,
      tone: "bg-destructive/12 text-destructive",
    },
    {
      label: "Cảnh báo mới",
      value: openAlerts,
      note: "Cần bác sĩ xem trong hôm nay",
      icon: AlertTriangle,
      tone: "bg-warning/25 text-warning-foreground",
    },
    {
      label: "Đơn thuốc đang chạy",
      value: prescriptions.length,
      note: "Đang có lịch nhắc hoặc theo dõi",
      icon: CalendarClock,
      tone: "bg-primary/10 text-primary",
    },
  ];

  // Goi y sinh TU SO LIEU vua tinh, khong con la 3 doan chu viet san. Chi hien
  // nhung y thuc su co can cu - khong co gi dang noi thi khong bia ra loi
  // khuyen chung chung.
  const goiY: { title: string; detail: string }[] = [];
  if (highRisk.length > 0) {
    const coCanhBao = highRisk.filter((p) =>
      canhBaoTrongPhamVi.some((a) => a.patientId === p.id && a.status === "new"),
    );
    goiY.push({
      title: "Ưu tiên trong hôm nay",
      detail:
        coCanhBao.length > 0
          ? `${coCanhBao.length}/${highRisk.length} bệnh nhân tuân thủ dưới 75% đang có cảnh báo chưa xử lý — xem trước nhóm này.`
          : `${highRisk.length} bệnh nhân tuân thủ dưới 75%, hiện chưa ai có cảnh báo mới.`,
    });
  }
  if (khungBoLoNhieuNhat && khungBoLoNhieuNhat.missed > 0) {
    goiY.push({
      title: "Điều chỉnh nhắc nhở",
      detail: `Bỏ lỡ tập trung vào buổi ${khungBoLoNhieuNhat.label.toLowerCase()} (${khungBoLoNhieuNhat.missed}/${tongBoLo} lượt) — cân nhắc đổi giờ nhắc hoặc thêm người thân theo dõi.`,
    });
  }
  const nghiemTrong = canhBaoTrongPhamVi.filter(
    (a: SysAlert) => a.level === "high" && a.status === "new",
  ).length;
  if (nghiemTrong > 0) {
    goiY.push({
      title: "Theo dõi an toàn",
      detail: `${nghiemTrong} cảnh báo mức nghiêm trọng chưa xử lý — nên xem trước các cảnh báo hành chính.`,
    });
  }

  if (theoDoi.length === 0) {
    return (
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
    );
  }

  return (
    <div className="space-y-5">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="surface-card flex items-start gap-4 p-5">
              <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-2xl ${s.tone}`}>
                <Icon className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <p className="text-sm text-muted-foreground">{s.label}</p>
                <p className="mt-1 text-3xl font-extrabold leading-none">{s.value}</p>
                <p className="mt-2 text-xs text-muted-foreground">{s.note}</p>
              </div>
            </div>
          );
        })}
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Phân bố mức tuân thủ</h2>
          <p className="text-sm text-muted-foreground">
            Số bệnh nhân theo từng nhóm tuân thủ.
            {chuaCoSoLieu > 0 && ` Chưa tính được ${chuaCoSoLieu} BN (chưa có liều đến hạn).`}
          </p>
          {coSoLieu.length === 0 ? (
            <p className="mt-6 text-sm text-muted-foreground">
              Chưa bệnh nhân nào có liều đến hạn nên chưa chia nhóm được.
            </p>
          ) : (
            <div className="mt-5 space-y-4">
              {nhomTuanThu.map((b) => (
                <div
                  key={b.key}
                  className="grid gap-2 sm:grid-cols-[180px_minmax(0,1fr)_72px] sm:items-center"
                >
                  <div>
                    <p className="text-sm font-semibold">{b.label}</p>
                    <p className="text-xs text-muted-foreground">{b.range}</p>
                  </div>
                  <div className="h-3 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full transition-[width]"
                      style={{ width: `${(b.value / bucketMax) * 100}%`, background: b.color }}
                    />
                  </div>
                  <p className="text-sm font-semibold text-muted-foreground sm:text-right">
                    {b.value} BN
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Tình trạng liều trong {SO_NGAY} ngày</h2>
          <p className="text-sm text-muted-foreground">Tỷ lệ dùng đúng, trễ và bỏ lỡ theo ngày.</p>

          {loadingSummary && (
            <p className="mt-6 text-sm text-muted-foreground">Đang tải…</p>
          )}
          {loiSummary && <p className="mt-6 text-sm text-destructive">{loiSummary}</p>}
          {summary && !loiSummary && (
            <div className="mt-5 space-y-4">
              {summary.daily.map((d) => {
                const pct = (n: number) => (d.total > 0 ? Math.round((n / d.total) * 100) : 0);
                return (
                  <div
                    key={d.date}
                    className="grid grid-cols-[64px_minmax(0,1fr)] items-center gap-3"
                  >
                    <p className="text-sm font-bold text-muted-foreground">
                      {tenThuVN(d.date)}
                      <span className="ml-1 font-normal text-xs">{ngayNgan(d.date)}</span>
                    </p>
                    <div>
                      <div className="flex h-3 overflow-hidden rounded-full bg-muted">
                        <div className="bg-success" style={{ width: `${pct(d.taken)}%` }} />
                        <div className="bg-warning" style={{ width: `${pct(d.delayed)}%` }} />
                        <div className="bg-destructive" style={{ width: `${pct(d.missed)}%` }} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {d.total === 0 ? (
                          "Không có liều nào đến hạn"
                        ) : (
                          <>
                            Đúng {pct(d.taken)}% · Trễ {pct(d.delayed)}% · Bỏ lỡ {pct(d.missed)}%
                            <span className="ml-1">({d.total} liều)</span>
                          </>
                        )}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-3">
        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Cảnh báo theo loại</h2>
          <p className="text-sm text-muted-foreground">
            Cảnh báo phát sinh trong {SO_NGAY} ngày gần nhất.
          </p>
          {loaiCanhBao.length === 0 ? (
            <p className="mt-6 text-sm text-muted-foreground">
              Không có cảnh báo nào trong {SO_NGAY} ngày qua.
            </p>
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
          {loadingSummary && <p className="mt-6 text-sm text-muted-foreground">Đang tải…</p>}
          {loiSummary && <p className="mt-6 text-sm text-destructive">{loiSummary}</p>}
          {summary && !loiSummary && tongBoLo === 0 && (
            <p className="mt-6 text-sm text-muted-foreground">
              Không có liều nào bị bỏ lỡ trong {SO_NGAY} ngày qua.
            </p>
          )}
          {summary && !loiSummary && tongBoLo > 0 && (
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
              Chưa bệnh nhân nào có đủ dữ liệu để xếp hạng.
            </p>
          ) : (
            <div className="mt-5 space-y-3">
              {uuTien.map((p) => {
                const nhom = nhomCua(p.adherence);
                return (
                  <div key={p.id} className="rounded-lg border border-border p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-bold" title={p.name}>
                          {p.name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {p.condition || "Chưa có ghi chú"}
                        </p>
                      </div>
                      <span
                        className="shrink-0 rounded-md px-2 py-1 text-xs font-bold"
                        style={{ background: `color-mix(in oklab, ${nhom.color} 14%, transparent)`, color: nhom.color }}
                      >
                        {nhom.label}
                      </span>
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${p.adherence}%`, background: nhom.color }}
                        />
                      </div>
                      <p className="w-14 text-right text-xs font-semibold">
                        {formatPercent(p.adherence)}%
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
