"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  ClipboardCheck,
  MoreVertical,
  Search,
  Users,
} from "lucide-react";
import { useState } from "react";
import { presentAlert } from "@/lib/alert-presentation";
import { useProto } from "@/lib/proto-store";

const riskTone: Record<string, string> = {
  Cao: "bg-destructive/12 text-destructive",
  "Trung bình": "bg-warning/25 text-warning-foreground",
  Thấp: "bg-success/15 text-success",
};

function barTone(v: number) {
  if (v >= 90) return "bg-success";
  if (v >= 70) return "bg-primary";
  if (v >= 50) return "bg-warning";
  return "bg-destructive";
}

function riskOf(adherence: number) {
  if (adherence < 75) return "Cao";
  if (adherence < 90) return "Trung bình";
  return "Thấp";
}

function formatDecimal(value: number) {
  if (!Number.isFinite(value)) return "0";
  if (Number.isInteger(value)) return String(value);

  const truncated = Math.trunc(value * 100) / 100;
  return truncated.toFixed(2);
}

const alertTone = {
  high: {
    bar: "bg-destructive",
    icon: "bg-destructive/12 text-destructive",
    chip: "border-destructive/40 text-destructive",
  },
  mid: {
    bar: "bg-warning",
    icon: "bg-warning/25 text-warning-foreground",
    chip: "border-warning/50 text-warning-foreground",
  },
  low: {
    bar: "bg-primary",
    icon: "bg-primary/10 text-primary",
    chip: "border-primary/40 text-primary",
  },
} as const;

const donut = [
  { label: "Tuân thủ tốt (≥ 90%)", sub: "35 bệnh nhân (27%)", color: "var(--success)", pct: 27 },
  {
    label: "Tuân thủ trung bình (70-89%)",
    sub: "62 bệnh nhân (48%)",
    color: "var(--primary)",
    pct: 48,
  },
  { label: "Tuân thủ kém (50-69%)", sub: "21 bệnh nhân (16%)", color: "var(--warning)", pct: 16 },
  {
    label: "Tuân thủ rất kém (< 50%)",
    sub: "10 bệnh nhân (8%)",
    color: "var(--destructive)",
    pct: 9,
  },
];

export default function DoctorDashboard() {
  const { patients, prescriptions, alerts } = useProto();
  const newAlerts = alerts.filter((a) => a.status === "new");
  const avg = patients.length
    ? Math.round(patients.reduce((s, p) => s + p.adherence, 0) / patients.length)
    : 0;
  const [q, setQ] = useState("");

  const watchedCount = patients.filter((p) => p.watch).length;
  const pendingPrescriptions = prescriptions.filter((p) => p.status === "pending").length;
  const highRiskCount = patients.filter((p) => riskOf(p.adherence) === "Cao").length;

  // Cac note "+N so voi tuan truoc" ban dau la chuoi bia cung, khong tinh tu
  // du lieu that (Patient/Prescription that khong luu snapshot theo tuan) -
  // thay bang so lieu phai/that da co san trong `patients`/`prescriptions`,
  // dung quy uoc note = so lieu phu that nhu admin/page.tsx dang dung.
  const stats = [
    {
      label: "Tổng bệnh nhân",
      value: patients.length,
      note:
        watchedCount > 0
          ? `${watchedCount} đang theo dõi đặc biệt`
          : "Chưa có ca theo dõi đặc biệt",
      noteTone: watchedCount > 0 ? "text-warning-foreground" : "text-muted-foreground",
      icon: Users,
      tone: "bg-primary/10 text-primary",
    },
    {
      label: "Đơn thuốc đang theo dõi",
      value: prescriptions.length,
      note:
        pendingPrescriptions > 0 ? `${pendingPrescriptions} chờ duyệt` : "Không có đơn chờ duyệt",
      noteTone: pendingPrescriptions > 0 ? "text-warning-foreground" : "text-success",
      icon: ClipboardCheck,
      tone: "bg-success/15 text-success",
    },
    {
      label: "Cảnh báo chưa xử lý",
      value: newAlerts.length,
      link: { to: "/doctor/alerts", label: "Xem chi tiết" },
      icon: Bell,
      tone: "bg-warning/25 text-warning-foreground",
    },
    {
      label: "Bệnh nhân nguy cơ cao",
      value: highRiskCount,
      note: "Tuân thủ dưới 75% (7 ngày)",
      noteTone: highRiskCount > 0 ? "text-destructive" : "text-success",
      icon: AlertTriangle,
      tone: "bg-destructive/12 text-destructive",
    },
  ];

  const list = patients.filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));
  let acc = 0;
  const gradient = donut
    .map((d) => {
      const from = acc;
      acc += d.pct;
      return `${d.color} ${from}% ${acc}%`;
    })
    .join(", ");

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="surface-card flex items-start gap-4 p-5">
              <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl ${s.tone}`}>
                <Icon className="h-6 w-6" />
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm text-muted-foreground">{s.label}</p>
                <p className="mt-1 text-3xl font-extrabold leading-none">{s.value}</p>
                {s.note && <p className={`mt-2 text-xs font-semibold ${s.noteTone}`}>{s.note}</p>}
                {s.link && (
                  <Link
                    href={s.link.to}
                    className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-primary"
                  >
                    {s.link.label} <ArrowRight className="h-3 w-3" />
                  </Link>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <section className="surface-card p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold">Bệnh nhân cần theo dõi</h2>
            <Link
              href="/doctor/patients"
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-primary"
            >
              Xem tất cả
            </Link>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <div className="relative min-w-[200px] flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Tìm kiếm bệnh nhân..."
                className="h-10 w-full rounded-xl border border-input bg-card pl-9 pr-3 text-sm outline-none focus:border-primary"
              />
            </div>
            <select className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none">
              <option>Trạng thái: Tất cả</option>
              <option>Đang theo dõi</option>
            </select>
            <select className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none">
              <option>Mức độ nguy cơ: Tất cả</option>
              <option>Cao</option>
            </select>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-y border-border bg-muted/60 text-left align-middle text-xs font-semibold text-muted-foreground">
                  <th className="px-3 py-3 align-middle">Bệnh nhân</th>
                  <th className="px-3 py-3 align-middle">Tuổi</th>
                  <th className="w-48 px-3 py-3 align-middle">Chẩn đoán chính</th>
                  <th className="px-3 py-3 align-middle">Mức độ nguy cơ</th>
                  <th className="whitespace-nowrap px-3 py-3 align-middle">Tuân thủ (7 ngày)</th>
                  <th className="whitespace-nowrap px-3 py-3 align-middle">Cập nhật cuối</th>
                  <th className="px-3 py-3 align-middle" />
                </tr>
              </thead>
              <tbody>
                {list.map((p, i) => {
                  const risk = riskOf(p.adherence);
                  return (
                    <tr key={p.id} className="border-b border-border last:border-0">
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-2.5">
                          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-xs font-bold text-accent-foreground">
                            {p.name.charAt(0)}
                          </span>
                          <div className="min-w-0">
                            <p className="truncate font-semibold text-primary">{p.name}</p>
                            <p className="text-xs text-muted-foreground">
                              ID: BN{String(i + 1).padStart(4, "0")}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-3">{p.age}</td>
                      <td className="px-3 py-3">{p.condition}</td>
                      <td className="px-3 py-3">
                        <span
                          className={`inline-block whitespace-nowrap rounded-md px-2 py-1 text-xs font-semibold ${riskTone[risk]}`}
                        >
                          {risk}
                        </span>
                      </td>
                      <td className="px-3 py-3">
                        <p className="text-xs font-semibold">{formatDecimal(p.adherence)}%</p>
                        <div className="mt-1 h-1.5 w-28 overflow-hidden rounded-full bg-muted">
                          <div
                            className={`h-full rounded-full ${barTone(p.adherence)}`}
                            style={{ width: `${p.adherence}%` }}
                          />
                        </div>
                      </td>
                      <td className="px-3 py-3 text-muted-foreground">Hôm nay, 08:30</td>
                      <td className="px-3 py-3 text-right">
                        <MoreVertical className="h-4 w-4 text-muted-foreground" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="surface-card p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold">Cảnh báo mới nhất</h2>
            <Link href="/doctor/alerts" className="text-xs font-semibold text-primary">
              Xem tất cả
            </Link>
          </div>
          <div className="mt-4 space-y-3">
            {alerts.slice(0, 3).map((a) => {
              const t = alertTone[a.level];
              const alert = presentAlert(a, patients);
              return (
                <div
                  key={a.id}
                  className="relative overflow-hidden rounded-xl border border-border p-4 pl-5"
                >
                  <span className={`absolute inset-y-0 left-0 w-1 ${t.bar}`} />
                  <div className="flex gap-3">
                    <span
                      className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${t.icon}`}
                    >
                      <AlertTriangle className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 font-semibold">{alert.title}</p>
                        <span
                          className={`shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${t.chip}`}
                        >
                          Cần xem
                        </span>
                      </div>
                      <p className="hidden">
                        {patients[0]?.name} · {a.at} hôm nay
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {alert.patientName} · {a.at} hôm nay · {alert.severityLabel} ·{" "}
                        {alert.statusLabel}
                      </p>
                      <p className="mt-1.5 text-sm font-medium text-foreground">{alert.problem}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{alert.evidence}</p>
                      <p className="mt-2 text-xs font-semibold text-primary">{alert.action}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <Link
            href="/doctor/alerts"
            className="mt-4 flex items-center justify-center gap-1.5 text-sm font-semibold text-primary"
          >
            Xem tất cả cảnh báo <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <section className="surface-card p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold">Tổng quan thông tin</h2>
            <select className="h-9 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none">
              <option>7 ngày qua</option>
              <option>30 ngày qua</option>
            </select>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-6">
            <div className="relative h-[170px] w-[170px] shrink-0">
              <div
                className="h-full w-full rounded-full"
                style={{ background: `conic-gradient(${gradient})` }}
              />
              <div className="absolute inset-[26px] grid place-items-center rounded-full bg-card">
                <div className="text-center">
                  <p className="text-3xl font-extrabold leading-none">{avg}%</p>
                  <p className="mt-1 text-xs text-muted-foreground">Trung bình</p>
                </div>
              </div>
            </div>
            <ul className="min-w-[190px] flex-1 space-y-3">
              {donut.map((d) => (
                <li key={d.label} className="flex gap-2.5">
                  <span
                    className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: d.color }}
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold leading-tight">{d.label}</p>
                    <p className="text-xs text-muted-foreground">{d.sub}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <Link
            href="/doctor/reports/adherence"
            className="mt-5 flex items-center justify-center gap-1.5 text-sm font-semibold text-primary"
          >
            Xem báo cáo chi tiết <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      </div>
    </div>
  );
}
