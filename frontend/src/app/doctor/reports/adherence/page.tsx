"use client";

import { Activity, AlertTriangle, CalendarClock, CheckCircle2, Clock3, Users } from "lucide-react";
import { useProto } from "@/lib/proto-store";

const adherenceBuckets = [
  { label: "Tuân thủ tốt", range: ">= 90%", value: 35, color: "var(--success)" },
  { label: "Trung bình", range: "70-89%", value: 62, color: "var(--primary)" },
  { label: "Kém", range: "50-69%", value: 21, color: "var(--warning)" },
  { label: "Rất kém", range: "< 50%", value: 10, color: "var(--destructive)" },
];

const weeklyDoses = [
  { day: "T2", taken: 78, missed: 8, delayed: 14 },
  { day: "T3", taken: 74, missed: 10, delayed: 16 },
  { day: "T4", taken: 82, missed: 6, delayed: 12 },
  { day: "T5", taken: 69, missed: 13, delayed: 18 },
  { day: "T6", taken: 76, missed: 9, delayed: 15 },
  { day: "T7", taken: 71, missed: 12, delayed: 17 },
  { day: "CN", taken: 66, missed: 15, delayed: 19 },
];

const alertTypes = [
  { label: "Bỏ lỡ liều", value: 42, color: "bg-warning" },
  { label: "Triệu chứng nguy hiểm", value: 18, color: "bg-destructive" },
  { label: "Tác dụng phụ", value: 16, color: "bg-primary" },
  { label: "Ảnh không khớp", value: 9, color: "bg-accent" },
];

const missedWindows = [
  { label: "Sáng", value: 18 },
  { label: "Trưa", value: 11 },
  { label: "Chiều", value: 15 },
  { label: "Tối", value: 27 },
];

function formatPercent(value: number) {
  if (!Number.isFinite(value)) return "0";
  if (Number.isInteger(value)) return String(value);
  return (Math.trunc(value * 100) / 100).toFixed(2);
}

function riskLabel(value: number) {
  if (value < 50) return "Rất kém";
  if (value < 70) return "Kém";
  if (value < 90) return "Trung bình";
  return "Tốt";
}

export default function ReportAdherence() {
  const { patients, alerts, prescriptions } = useProto();
  const avg =
    patients.length > 0 ? patients.reduce((s, p) => s + p.adherence, 0) / patients.length : 0;
  const openAlerts = alerts.filter((a) => a.status === "new").length;
  const highRiskPatients = patients.filter((p) => p.adherence < 75);
  const bucketMax = Math.max(...adherenceBuckets.map((b) => b.value));
  const alertMax = Math.max(...alertTypes.map((a) => a.value));
  const missedMax = Math.max(...missedWindows.map((w) => w.value));

  const stats = [
    {
      label: "Tuân thủ trung bình",
      value: `${formatPercent(avg)}%`,
      note: "Theo toàn bộ bệnh nhân đang theo dõi",
      icon: CheckCircle2,
      tone: "bg-success/15 text-success",
    },
    {
      label: "Bệnh nhân nguy cơ cao",
      value: highRiskPatients.length,
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

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Tổng quan thông tin</h1>
        <p className="text-sm text-muted-foreground">
          Tóm tắt nhanh tình hình tuân thủ, cảnh báo và các nhóm bệnh nhân cần ưu tiên theo dõi.
        </p>
      </header>

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
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold">Phân bố mức tuân thủ</h2>
              <p className="text-sm text-muted-foreground">Số bệnh nhân theo từng nhóm tuân thủ.</p>
            </div>
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-semibold text-muted-foreground">
              Mock
            </span>
          </div>
          <div className="mt-5 space-y-4">
            {adherenceBuckets.map((b) => (
              <div
                key={b.label}
                className="grid gap-2 sm:grid-cols-[180px_minmax(0,1fr)_72px] sm:items-center"
              >
                <div>
                  <p className="text-sm font-semibold">{b.label}</p>
                  <p className="text-xs text-muted-foreground">{b.range}</p>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${(b.value / bucketMax) * 100}%`, background: b.color }}
                  />
                </div>
                <p className="text-sm font-semibold text-muted-foreground sm:text-right">
                  {b.value} BN
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="surface-card p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold">Tình trạng liều trong 7 ngày</h2>
              <p className="text-sm text-muted-foreground">
                Tỷ lệ dùng đúng, trễ và bỏ lỡ theo ngày.
              </p>
            </div>
            <Activity className="h-5 w-5 text-primary" />
          </div>
          <div className="mt-5 space-y-4">
            {weeklyDoses.map((d) => (
              <div key={d.day} className="grid grid-cols-[34px_minmax(0,1fr)] items-center gap-3">
                <p className="text-sm font-bold text-muted-foreground">{d.day}</p>
                <div>
                  <div className="flex h-3 overflow-hidden rounded-full bg-muted">
                    <div className="bg-success" style={{ width: `${d.taken}%` }} />
                    <div className="bg-warning" style={{ width: `${d.delayed}%` }} />
                    <div className="bg-destructive" style={{ width: `${d.missed}%` }} />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Đúng {d.taken}% · Trễ {d.delayed}% · Bỏ lỡ {d.missed}%
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-3">
        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Cảnh báo theo loại</h2>
          <p className="text-sm text-muted-foreground">Ước lượng số cảnh báo trong tuần.</p>
          <div className="mt-5 space-y-4">
            {alertTypes.map((a) => (
              <div key={a.label}>
                <div className="mb-1 flex items-center justify-between gap-3 text-sm">
                  <span className="font-semibold">{a.label}</span>
                  <span className="text-muted-foreground">{a.value}</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full rounded-full ${a.color}`}
                    style={{ width: `${(a.value / alertMax) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Khung giờ hay bỏ lỡ</h2>
          <p className="text-sm text-muted-foreground">Giúp bác sĩ điều chỉnh nhắc nhở khi cần.</p>
          <div className="mt-5 flex h-48 items-end gap-4">
            {missedWindows.map((w) => (
              <div key={w.label} className="flex min-w-0 flex-1 flex-col items-center gap-2">
                <div className="flex h-36 w-full items-end rounded-lg bg-muted/60 px-2">
                  <div
                    className="w-full rounded-t-md bg-primary"
                    style={{ height: `${(w.value / missedMax) * 100}%` }}
                  />
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold">{w.value}</p>
                  <p className="text-xs text-muted-foreground">{w.label}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="surface-card p-6">
          <h2 className="text-lg font-bold">Bệnh nhân cần ưu tiên</h2>
          <p className="text-sm text-muted-foreground">Xếp theo tỷ lệ tuân thủ thấp nhất.</p>
          <div className="mt-5 space-y-3">
            {[...patients]
              .sort((a, b) => a.adherence - b.adherence)
              .slice(0, 4)
              .map((p) => (
                <div key={p.id} className="rounded-lg border border-border p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold">{p.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {p.condition || "Chưa có ghi chú"}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-md bg-destructive/12 px-2 py-1 text-xs font-bold text-destructive">
                      {riskLabel(p.adherence)}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-warning"
                        style={{ width: `${p.adherence}%` }}
                      />
                    </div>
                    <p className="w-14 text-right text-xs font-semibold">
                      {formatPercent(p.adherence)}%
                    </p>
                  </div>
                </div>
              ))}
          </div>
        </div>
      </section>

      <section className="surface-card p-6">
        <div className="flex items-center gap-2">
          <Clock3 className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-bold">Gợi ý đọc nhanh cho bác sĩ</h2>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-lg bg-muted/45 p-4">
            <p className="text-sm font-bold">Ưu tiên trong hôm nay</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Xem trước bệnh nhân có tuân thủ dưới 75% và đang có cảnh báo mới.
            </p>
          </div>
          <div className="rounded-lg bg-muted/45 p-4">
            <p className="text-sm font-bold">Điều chỉnh nhắc nhở</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Nếu bỏ lỡ tập trung buổi tối, cân nhắc đổi giờ nhắc hoặc thêm người thân theo dõi.
            </p>
          </div>
          <div className="rounded-lg bg-muted/45 p-4">
            <p className="text-sm font-bold">Theo dõi an toàn</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Cảnh báo triệu chứng nguy hiểm và quá liều cần được xem trước các cảnh báo hành chính.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
