"use client";

import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  FileClock,
  Link2,
  PillBottle,
  ShieldAlert,
  Users2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { MEDICINES, SYSTEM_AUDIT, roleLabel } from "@/lib/admin-mock";
import { listAccounts, type AccountRecord } from "@/lib/accounts";
import { listCaregiverLinksForPatient } from "@/lib/caregivers";
import { listReportingPatients } from "@/lib/reporting";

const roleBadgeTone: Record<string, string> = {
  doctor: "bg-success/15 text-success",
  patient: "bg-primary/10 text-primary",
  caregiver: "bg-warning/25 text-warning-foreground",
  admin: "bg-accent text-accent-foreground",
  "Hệ thống": "bg-muted text-muted-foreground",
};

export default function AdminDashboard() {
  const [accounts, setAccounts] = useState<AccountRecord[]>([]);
  const [linkCount, setLinkCount] = useState(0);
  const [patientCount, setPatientCount] = useState(0);

  useEffect(() => {
    listAccounts()
      .then(setAccounts)
      .catch(() => undefined);
    listReportingPatients()
      .then(async (patients) => {
        setPatientCount(patients.length);
        const lists = await Promise.all(
          patients.map((p) => listCaregiverLinksForPatient(p.id).catch(() => [])),
        );
        setLinkCount(lists.reduce((sum, l) => sum + l.length, 0));
      })
      .catch(() => undefined);
  }, []);

  const total = accounts.length;
  const pending = accounts.filter((a) => a.status === "pending").length;
  const locked = accounts.filter((a) => a.status === "locked").length;
  const indexed = MEDICINES.filter((m) => m.status === "indexed").length;
  const needsAttention = MEDICINES.filter((m) => m.status !== "indexed").length;

  const roleCounts = {
    patient: accounts.filter((a) => a.role === "patient").length,
    doctor: accounts.filter((a) => a.role === "doctor").length,
    caregiver: accounts.filter((a) => a.role === "caregiver").length,
    admin: accounts.filter((a) => a.role === "admin").length,
  };
  const pctOf = (n: number) => (total > 0 ? (n / total) * 100 : 0);
  const donut = [
    {
      label: "Bệnh nhân",
      sub: `${roleCounts.patient} tài khoản`,
      color: "var(--primary)",
      pct: pctOf(roleCounts.patient),
    },
    {
      label: "Bác sĩ",
      sub: `${roleCounts.doctor} tài khoản`,
      color: "var(--success)",
      pct: pctOf(roleCounts.doctor),
    },
    {
      label: "Người thân",
      sub: `${roleCounts.caregiver} tài khoản`,
      color: "var(--warning)",
      pct: pctOf(roleCounts.caregiver),
    },
    {
      label: "Quản trị",
      sub: `${roleCounts.admin} tài khoản`,
      color: "var(--muted-foreground)",
      pct: pctOf(roleCounts.admin),
    },
  ];

  const stats = [
    {
      label: "Tổng tài khoản",
      value: total,
      note: `${pending} chờ kích hoạt · ${locked} đã khoá`,
      noteTone: pending || locked ? "text-warning-foreground" : "text-success",
      icon: Users2,
      tone: "bg-primary/10 text-primary",
      link: { to: "/admin/accounts", label: "Quản lý tài khoản" },
    },
    {
      label: "Liên kết người thân đang hoạt động",
      value: linkCount,
      note: "Bệnh nhân ↔ người thân",
      noteTone: "text-muted-foreground",
      icon: Link2,
      tone: "bg-success/15 text-success",
      link: { to: "/admin/links", label: "Xem liên kết" },
    },
    {
      label: "Dữ liệu thuốc (RAG)",
      value: `${indexed}/${MEDICINES.length}`,
      note: `${needsAttention} bản ghi cần xử lý`,
      noteTone: needsAttention ? "text-warning-foreground" : "text-success",
      icon: PillBottle,
      tone: "bg-warning/25 text-warning-foreground",
      link: { to: "/admin/medicines", label: "Quản lý dữ liệu thuốc" },
      mock: true,
    },
    {
      label: "Sự kiện hệ thống gần đây",
      value: SYSTEM_AUDIT.length,
      note: "Xem toàn bộ audit log",
      noteTone: "text-muted-foreground",
      icon: FileClock,
      tone: "bg-accent text-accent-foreground",
      link: { to: "/admin/audit", label: "Xem log hệ thống" },
      mock: true,
    },
  ];

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
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1.5 truncate text-sm text-muted-foreground">
                  {s.label}
                  {"mock" in s && s.mock && (
                    <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold">
                      Mock
                    </span>
                  )}
                </p>
                <p className="mt-1 text-3xl font-extrabold leading-none">{s.value}</p>
                <p className={`mt-2 truncate text-xs font-semibold ${s.noteTone}`}>{s.note}</p>
                <Link
                  href={s.link.to}
                  className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-primary"
                >
                  {s.link.label} <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <section className="surface-card p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold">Phân bổ tài khoản theo vai trò</h2>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-6">
            <div className="relative h-[170px] w-[170px] shrink-0">
              <div
                className="h-full w-full rounded-full"
                style={{ background: `conic-gradient(${gradient})` }}
              />
              <div className="absolute inset-[26px] grid place-items-center rounded-full bg-card">
                <div className="text-center">
                  <p className="text-3xl font-extrabold leading-none">{total}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Tài khoản</p>
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
            href="/admin/accounts"
            className="mt-5 flex items-center justify-center gap-1.5 text-sm font-semibold text-primary"
          >
            Quản lý tất cả tài khoản <ArrowRight className="h-4 w-4" />
          </Link>
        </section>

        <section className="surface-card p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-lg font-bold">
              Hoạt động hệ thống gần đây
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                Mock
              </span>
            </h2>
            <Link href="/admin/audit" className="text-xs font-semibold text-primary">
              Xem tất cả
            </Link>
          </div>
          <div className="mt-4 divide-y divide-border">
            {SYSTEM_AUDIT.slice(0, 5).map((a) => (
              <div key={a.id} className="flex items-start gap-3 py-3">
                <span className="w-12 shrink-0 pt-0.5 font-mono text-xs text-muted-foreground">
                  {a.at}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold" title={a.actor}>
                    {a.actor}
                  </p>
                  <p className="text-sm text-muted-foreground">{a.action}</p>
                </div>
                <span
                  className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ${roleBadgeTone[a.role] ?? "bg-muted text-muted-foreground"}`}
                >
                  {a.role === "Hệ thống" ? "Hệ thống" : roleLabel[a.role as keyof typeof roleLabel]}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="surface-card p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-lg font-bold">
            <ShieldAlert className="h-5 w-5 text-warning-foreground" /> Cần chú ý
          </h2>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-border p-4">
            <p className="flex items-center gap-2 text-sm font-semibold">
              <Users2 className="h-4 w-4 text-primary" /> {pending} tài khoản chờ kích hoạt
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Cần xác minh và cấp quyền trước khi cho đăng nhập.
            </p>
            <Link
              href="/admin/accounts"
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-primary"
            >
              Xử lý ngay <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="rounded-xl border border-border p-4">
            <p className="flex items-center gap-2 text-sm font-semibold">
              <PillBottle className="h-4 w-4 text-warning-foreground" /> {needsAttention} dữ liệu
              thuốc chưa index xong
              <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
                Mock
              </span>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Agent RAG có thể trả lời thiếu chính xác nếu chưa xử lý.
            </p>
            <Link
              href="/admin/medicines"
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-primary"
            >
              Kiểm tra <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="rounded-xl border border-border p-4">
            <p className="flex items-center gap-2 text-sm font-semibold">
              <Link2 className="h-4 w-4 text-primary" /> {patientCount} bệnh nhân trong hệ thống
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Xem liên kết người thân của từng bệnh nhân.
            </p>
            <Link
              href="/admin/links"
              className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-primary"
            >
              Xem chi tiết <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
