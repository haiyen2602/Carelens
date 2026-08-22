"use client";

import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  FileClock,
  Loader2,
  PillBottle,
  ShieldAlert,
  Users2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { MEDICINES } from "@/lib/admin-mock";
import { listAccounts, type AccountRecord } from "@/lib/accounts";
import { listSystemAuditLogs, type SystemAuditLogEntry } from "@/lib/audit";
import { useAuth } from "@/lib/auth";

const roleBadgeTone: Record<string, string> = {
  doctor: "bg-success/15 text-success",
  patient: "bg-primary/10 text-primary",
  caregiver: "bg-warning/25 text-warning-foreground",
  admin: "bg-accent text-accent-foreground",
  system: "bg-muted text-muted-foreground",
  "Hệ thống": "bg-muted text-muted-foreground",
};

const roleDisplayName: Record<string, string> = {
  admin: "Quản trị",
  doctor: "Bác sĩ",
  patient: "Bệnh nhân",
  caregiver: "Người thân",
  system: "Hệ thống",
  "Hệ thống": "Hệ thống",
};

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isCleanTarget(target?: string | null): boolean {
  if (!target) return false;
  return !UUID_REGEX.test(target.trim());
}

function formatDateTime(isoString: string) {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return { date: isoString, time: "" };
    const date = d.toLocaleDateString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
    const time = d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    return { date, time };
  } catch {
    return { date: isoString, time: "" };
  }
}

export default function AdminDashboard() {
  const { accessToken } = useAuth();
  const [accounts, setAccounts] = useState<AccountRecord[]>([]);
  const [recentAuditLogs, setRecentAuditLogs] = useState<SystemAuditLogEntry[]>([]);
  const [auditTotalCount, setAuditTotalCount] = useState(0);
  const [auditLoading, setAuditLoading] = useState(true);

  useEffect(() => {
    listAccounts()
      .then(setAccounts)
      .catch(() => undefined);

    listSystemAuditLogs({ pageSize: 5, accessToken })
      .then((res) => {
        setRecentAuditLogs(res.items);
        setAuditTotalCount(res.total);
      })
      .catch(() => undefined)
      .finally(() => setAuditLoading(false));
  }, [accessToken]);

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
      value: auditTotalCount,
      note: "Xem toàn bộ audit log",
      noteTone: "text-muted-foreground",
      icon: FileClock,
      tone: "bg-accent text-accent-foreground",
      link: { to: "/admin/audit", label: "Xem log hệ thống" },
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
            <div key={s.label} className="surface-card relative flex flex-col justify-between p-5">
              {s.mock && (
                <span className="absolute right-4 top-4 rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                  Mock
                </span>
              )}
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold text-muted-foreground">{s.label}</p>
                  <p className="mt-2 text-2xl font-extrabold">{s.value}</p>
                </div>
                <span className={`grid h-11 w-11 place-items-center rounded-2xl ${s.tone}`}>
                  <Icon className="h-5 w-5" />
                </span>
              </div>
              <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-xs">
                <span className={s.noteTone}>{s.note}</span>
                <Link
                  href={s.link.to}
                  className="inline-flex items-center gap-1 font-semibold text-primary"
                >
                  {s.link.label} <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="surface-card p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold">Phân bổ tài khoản theo vai trò</h2>
            <span className="text-xs text-muted-foreground">{total} tài khoản</span>
          </div>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-8">
            <div
              className="relative h-44 w-44 rounded-full p-4"
              style={{
                background: total > 0 ? `conic-gradient(${gradient})` : "var(--muted)",
              }}
              aria-hidden
            >
              <div
                className="absolute inset-[13px] rounded-full"
                style={{
                  background:
                    total > 0
                      ? `conic-gradient(${gradient})`
                      : "color-mix(in srgb, var(--foreground) 6%, transparent)",
                }}
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
            <h2 className="text-lg font-bold">
              Hoạt động hệ thống gần đây
            </h2>
            <Link href="/admin/audit" className="text-xs font-semibold text-primary">
              Xem tất cả
            </Link>
          </div>
          <div className="mt-4 divide-y divide-border">
            {auditLoading ? (
              <div className="py-8 text-center text-muted-foreground">
                <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
                <p className="mt-2 text-xs">Đang tải hoạt động gần đây...</p>
              </div>
            ) : recentAuditLogs.length === 0 ? (
              <p className="py-8 text-center text-xs text-muted-foreground">
                Chưa có hoạt động nào được ghi nhận.
              </p>
            ) : (
              recentAuditLogs.map((a) => {
                const { date, time } = formatDateTime(a.created_at);
                return (
                  <div key={a.id} className="flex items-start gap-3 py-3">
                    <div className="w-20 shrink-0 pt-0.5">
                      <p className="text-xs font-medium text-foreground">{date}</p>
                      {time && <p className="font-mono text-[11px] text-muted-foreground">{time}</p>}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold" title={a.actor_name}>
                        {a.actor_name}
                      </p>
                      <p className="text-xs text-muted-foreground">{a.action}</p>
                      {isCleanTarget(a.target) && (
                        <p className="mt-0.5 text-[11px] text-muted-foreground">
                          Đối tượng: {a.target}
                        </p>
                      )}
                    </div>
                    <span
                      className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ${roleBadgeTone[a.actor_role] ?? "bg-muted text-muted-foreground"}`}
                    >
                      {roleDisplayName[a.actor_role] ?? a.actor_role}
                    </span>
                  </div>
                );
              })
            )}
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
        </div>
      </section>
    </div>
  );
}
