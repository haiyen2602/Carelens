"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, ClipboardCheck, Search, Users } from "lucide-react";
import { useEffect, useState } from "react";
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

// 4 muc tuan thu dung CHUNG nguong voi riskOf() (Cao/Trung binh/Thap o bang
// ben trai) - CHI khac cach chia (4 bac thay vi 3) de khop UI dashboard cu.
// Dem THAT tu `patients` (adherence_pct that tu backend, xem lib/reporting.ts),
// KHONG con la mock co dinh 35/62/21/10.
const ADHERENCE_BUCKETS = [
  {
    key: "good",
    label: "Tuân thủ tốt (≥ 90%)",
    color: "var(--success)",
    test: (v: number) => v >= 90,
  },
  {
    key: "mid",
    label: "Tuân thủ trung bình (70-89%)",
    color: "var(--primary)",
    test: (v: number) => v >= 70 && v < 90,
  },
  {
    key: "poor",
    label: "Tuân thủ kém (50-69%)",
    color: "var(--warning)",
    test: (v: number) => v >= 50 && v < 70,
  },
  {
    key: "veryPoor",
    label: "Tuân thủ rất kém (< 50%)",
    color: "var(--destructive)",
    test: (v: number) => v < 50,
  },
] as const;

type StatusFilter = "all" | "watching";
type RiskFilter = "all" | "Cao" | "Trung bình" | "Thấp";

export default function DoctorDashboard() {
  const { patients, prescriptions, alerts } = useProto();
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");

  const avg =
    patients.length > 0
      ? Math.round(patients.reduce((s, p) => s + p.adherence, 0) / patients.length)
      : 0;

  const watchedCount = patients.filter((p) => p.watch).length;
  const pendingPrescriptions = prescriptions.filter((p) => p.status === "pending").length;

  // Cac note "+N so voi tuan truoc" ban dau la chuoi bia cung, khong tinh tu
  // du lieu that (Patient/Prescription that khong luu snapshot theo tuan) -
  // thay bang so lieu that da co san trong `patients`/`prescriptions`, dung
  // quy uoc note = so lieu phu that nhu admin/page.tsx dang dung.
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
  ];

  const list = patients.filter((p) => {
    if (!p.name.toLowerCase().includes(q.toLowerCase())) return false;
    if (statusFilter === "watching" && !p.watch) return false;
    if (riskFilter !== "all" && riskOf(p.adherence) !== riskFilter) return false;
    return true;
  });

  // Phan trang - toi da 10 benh nhan/trang. Reset ve trang 1 moi khi bo loc
  // doi (khong reset thi vd dang o trang 3, loc con 1 trang se hien bang
  // rong du data van con, xem useEffect ben duoi).
  const PAGE_SIZE = 10;
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages);
  const pageList = list.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [q, statusFilter, riskFilter]);

  // Phan bo THAT theo adherence_pct cua tung benh nhan (khong con la mock co
  // dinh) - tong so dong cua 4 bucket LUON = patients.length.
  const donut = ADHERENCE_BUCKETS.map((b) => ({
    ...b,
    count: patients.filter((p) => b.test(p.adherence)).length,
  }));
  const total = patients.length;
  let acc = 0;
  const gradient =
    total === 0
      ? "var(--muted) 0% 100%"
      : donut
          .map((d) => {
            const from = acc;
            acc += (d.count / total) * 100;
            return `${d.color} ${from}% ${acc}%`;
          })
          .join(", ");

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)] xl:items-stretch">
        <section className="surface-card flex min-h-0 flex-col p-5 xl:h-full">
          <div className="flex shrink-0 items-center justify-between gap-3">
            <h2 className="text-lg font-bold">Bệnh nhân cần theo dõi</h2>
            <Link
              href="/doctor/patients"
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-primary"
            >
              Xem tất cả
            </Link>
          </div>

          <div className="mt-4 flex shrink-0 flex-wrap gap-2">
            <div className="relative min-w-[200px] flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Tìm kiếm bệnh nhân..."
                className="h-10 w-full rounded-xl border border-input bg-card pl-9 pr-3 text-sm outline-none focus:border-primary"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
            >
              <option value="all">Trạng thái: Tất cả</option>
              <option value="watching">Đang theo dõi</option>
            </select>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value as RiskFilter)}
              className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
            >
              <option value="all">Mức độ nguy cơ: Tất cả</option>
              <option value="Cao">Cao</option>
              <option value="Trung bình">Trung bình</option>
              <option value="Thấp">Thấp</option>
            </select>
          </div>

          <div className="mt-4 min-h-0 flex-1 overflow-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead className="sticky top-0 z-10 bg-card">
                <tr className="border-y border-border bg-muted/60 text-left align-middle text-xs font-semibold text-muted-foreground">
                  <th className="px-3 py-3 align-middle">Bệnh nhân</th>
                  <th className="px-3 py-3 align-middle">Tuổi</th>
                  <th className="w-48 px-3 py-3 align-middle">Chẩn đoán chính</th>
                  <th className="px-3 py-3 align-middle">Mức độ nguy cơ</th>
                  <th className="whitespace-nowrap px-3 py-3 align-middle">Tuân thủ (7 ngày)</th>
                </tr>
              </thead>
              <tbody>
                {pageList.map((p) => {
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
                            <p className="text-xs text-muted-foreground">ID: {p.id}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-3">{p.age || "—"}</td>
                      <td className="px-3 py-3">{p.condition || "—"}</td>
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
                    </tr>
                  );
                })}
                {list.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-8 text-center text-sm text-muted-foreground">
                      Không tìm thấy bệnh nhân phù hợp.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {list.length > 0 && (
            <div className="mt-3 flex shrink-0 items-center justify-between gap-3 text-xs text-muted-foreground">
              <p>
                Trang {pageSafe}/{totalPages} · {list.length} bệnh nhân
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={pageSafe <= 1}
                  onClick={() => setPage(pageSafe - 1)}
                  className="rounded-lg border border-border px-3 py-1.5 font-semibold text-foreground disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Trước
                </button>
                <button
                  type="button"
                  disabled={pageSafe >= totalPages}
                  onClick={() => setPage(pageSafe + 1)}
                  className="rounded-lg border border-border px-3 py-1.5 font-semibold text-foreground disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Sau
                </button>
              </div>
            </div>
          )}
        </section>

        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4">
            {stats.map((s) => {
              const Icon = s.icon;
              return (
                <div key={s.label} className="surface-card flex items-start gap-3 p-4">
                  <span
                    className={`grid h-11 w-11 shrink-0 place-items-center rounded-2xl ${s.tone}`}
                  >
                    <Icon className="h-5 w-5" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-xs text-muted-foreground">{s.label}</p>
                    <p className="mt-0.5 text-2xl font-extrabold leading-none">{s.value}</p>
                    {s.note && (
                      <p className={`mt-1.5 truncate text-[11px] font-semibold ${s.noteTone}`}>
                        {s.note}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <section className="surface-card p-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold">Cảnh báo mới nhất</h2>
              <Link href="/doctor/alerts" className="text-xs font-semibold text-primary">
                Xem tất cả
              </Link>
            </div>
            <div className="mt-4 max-h-[280px] space-y-3 overflow-auto">
              {alerts.length === 0 && watchedCount === 0 && (
                <p className="text-sm text-muted-foreground">
                  Bạn chưa theo dõi bệnh nhân nào nên chưa có cảnh báo để hiển thị — bấm{" "}
                  <span className="font-semibold text-foreground">Theo dõi</span> ở trang{" "}
                  <Link href="/doctor/patients" className="font-semibold text-primary">
                    Quản lý bệnh nhân
                  </Link>{" "}
                  để nhận cảnh báo của họ tại đây.
                </p>
              )}
              {alerts.length === 0 && watchedCount > 0 && (
                <p className="text-sm text-muted-foreground">
                  Chưa có cảnh báo nào cho {watchedCount} bệnh nhân bạn đang theo dõi.
                </p>
              )}
              {alerts.slice(0, 3).map((a) => {
                const t = alertTone[a.level];
                const alert = presentAlert(a, patients);
                return (
                  <div
                    key={a.id}
                    className="relative overflow-hidden rounded-xl border border-border p-3 pl-4"
                  >
                    <span className={`absolute inset-y-0 left-0 w-1 ${t.bar}`} />
                    <div className="flex gap-3">
                      <span
                        className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${t.icon}`}
                      >
                        <AlertTriangle className="h-4 w-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <p className="min-w-0 truncate font-semibold">{alert.title}</p>
                          <span
                            className={`shrink-0 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${t.chip}`}
                          >
                            Cần xem
                          </span>
                        </div>
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                          {alert.patientName} · {a.at} hôm nay · {alert.severityLabel} ·{" "}
                          {alert.statusLabel}
                        </p>
                        <p className="mt-1.5 truncate text-sm font-medium text-foreground">
                          {alert.problem}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="surface-card shrink-0 p-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold">Tổng quan thông tin</h2>
            </div>
            <div className="mt-4 flex items-center gap-5">
              <div className="relative h-[110px] w-[110px] shrink-0">
                <div
                  className="h-full w-full rounded-full"
                  style={{ background: `conic-gradient(${gradient})` }}
                />
                <div className="absolute inset-[18px] grid place-items-center rounded-full bg-card">
                  <div className="text-center">
                    <p className="text-xl font-extrabold leading-none">{avg}%</p>
                    <p className="mt-1 text-[10px] text-muted-foreground">Trung bình</p>
                  </div>
                </div>
              </div>
              <ul className="min-w-0 flex-1 space-y-1.5">
                {donut.map((d) => (
                  <li key={d.key} className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: d.color }}
                    />
                    <p className="min-w-0 truncate text-xs text-muted-foreground">
                      {d.label}{" "}
                      <span className="text-foreground">
                        · {d.count} bệnh nhân ({total > 0 ? Math.round((d.count / total) * 100) : 0}
                        %)
                      </span>
                    </p>
                  </li>
                ))}
              </ul>
            </div>
            <Link
              href="/doctor/reports/adherence"
              className="mt-3 flex items-center justify-center gap-1.5 text-sm font-semibold text-primary"
            >
              Xem báo cáo chi tiết <ArrowRight className="h-4 w-4" />
            </Link>
          </section>
        </div>
      </div>
    </div>
  );
}
