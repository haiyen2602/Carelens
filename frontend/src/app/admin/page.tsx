"use client";

import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  FileClock,
  Inbox,
  Loader2,
  Lock,
  PillBottle,
  ShieldCheck,
  Stethoscope,
  Users,
  Users2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { listAccounts, type AccountRecord } from "@/lib/accounts";
import { listAdminDrugs } from "@/lib/admin-drugs";
import { listAllDrugRequests } from "@/lib/drug-requests";
import { listSystemAuditLogs, type SystemAuditLogEntry } from "@/lib/audit";
import { useAuth } from "@/lib/auth";

const roleBadgeTone: Record<string, string> = {
  doctor: "bg-success/15 text-success",
  patient: "bg-primary/10 text-primary",
  caregiver: "bg-warning/25 text-warning-foreground",
  admin: "bg-accent text-accent-foreground",
  super_admin: "bg-accent text-accent-foreground",
  system: "bg-muted text-muted-foreground",
  "Hệ thống": "bg-muted text-muted-foreground",
};

const roleDisplayName: Record<string, string> = {
  admin: "Quản trị",
  super_admin: "Quản trị cấp cao",
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
  const [drugTotalCount, setDrugTotalCount] = useState<number | null>(null);
  const [pendingDrugRequestsCount, setPendingDrugRequestsCount] = useState<number | null>(null);
  const [recentAuditLogs, setRecentAuditLogs] = useState<SystemAuditLogEntry[]>([]);
  const [auditTotalCount, setAuditTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;

    setLoading(true);
    Promise.allSettled([
      listAccounts(accessToken).then(setAccounts),
      listAdminDrugs({ page: 1, pageSize: 1, accessToken }).then((res) =>
        setDrugTotalCount(res.total),
      ),
      listAllDrugRequests("PENDING", accessToken).then((items) =>
        setPendingDrugRequestsCount(items.length),
      ),
      listSystemAuditLogs({ pageSize: 5, accessToken }).then((res) => {
        setRecentAuditLogs(res.items);
        setAuditTotalCount(res.total);
      }),
    ]).finally(() => setLoading(false));
  }, [accessToken]);

  const total = accounts.length;
  const pending = accounts.filter((a) => a.status === "pending").length;
  const locked = accounts.filter((a) => a.status === "locked").length;

  const roleCounts = {
    patient: accounts.filter((a) => a.role === "patient").length,
    doctor: accounts.filter((a) => a.role === "doctor").length,
    admin: accounts.filter((a) => a.role === "admin").length,
    superAdmin: accounts.filter((a) => (a.role as string) === "super_admin").length,
  };
  const pctOf = (n: number) => (total > 0 ? (n / total) * 100 : 0);
  const donut = [
    {
      label: "Bệnh nhân",
      count: roleCounts.patient,
      sub: `${roleCounts.patient} tài khoản`,
      color: "var(--primary)",
      pct: pctOf(roleCounts.patient),
    },
    {
      label: "Bác sĩ",
      count: roleCounts.doctor,
      sub: `${roleCounts.doctor} tài khoản`,
      color: "var(--success)",
      pct: pctOf(roleCounts.doctor),
    },
    {
      label: "Quản trị",
      count: roleCounts.admin,
      sub: `${roleCounts.admin} tài khoản`,
      color: "var(--accent-foreground)",
      pct: pctOf(roleCounts.admin),
    },
    {
      label: "Quản trị cấp cao",
      count: roleCounts.superAdmin,
      sub: `${roleCounts.superAdmin} tài khoản`,
      color: "oklch(0.55 0.22 295)",
      pct: pctOf(roleCounts.superAdmin),
    },
  ];

  const stats = [
    {
      label: "Tổng tài khoản",
      value: loading && accounts.length === 0 ? "..." : total,
      note: `${pending} chờ kích hoạt · ${locked} đã khoá`,
      noteTone: pending || locked ? "text-warning-foreground" : "text-success",
      icon: Users2,
      tone: "bg-primary/10 text-primary",
      link: { to: "/admin/accounts", label: "Quản lý tài khoản" },
    },
    {
      label: "Dữ liệu thuốc (RAG)",
      value: drugTotalCount !== null ? drugTotalCount : (loading ? "..." : "0"),
      note: "Kho tri thức dược lâm sàng",
      noteTone: "text-success",
      icon: PillBottle,
      tone: "bg-success/15 text-success",
      link: { to: "/admin/medicines", label: "Quản lý dữ liệu thuốc" },
    },
    {
      label: "Yêu cầu bổ sung thuốc",
      value:
        pendingDrugRequestsCount !== null
          ? pendingDrugRequestsCount
          : (loading ? "..." : "0"),
      note:
        (pendingDrugRequestsCount ?? 0) > 0
          ? `${pendingDrugRequestsCount} yêu cầu đang chờ duyệt`
          : "Không có yêu cầu chờ",
      noteTone:
        (pendingDrugRequestsCount ?? 0) > 0 ? "text-warning-foreground" : "text-success",
      icon: Inbox,
      tone: "bg-warning/25 text-warning-foreground",
      link: { to: "/admin/drug-requests", label: "Xử lý yêu cầu" },
    },
    {
      label: "Sự kiện hệ thống",
      value: loading && auditTotalCount === 0 ? "..." : auditTotalCount,
      note: "Xem toàn bộ nhật ký kiểm toán",
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
        <section className="surface-card flex flex-col justify-between p-5 space-y-5">
          {/* Header */}
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-foreground">Phân bổ tài khoản theo vai trò</h2>
              <p className="text-xs text-muted-foreground">Tỷ lệ cơ cấu người dùng &amp; tình trạng tài khoản</p>
            </div>
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
              {total} tài khoản
            </span>
          </div>

          {/* Tier 1: Donut & Detailed Legends with Percentage */}
          <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-8">
            <div
              className="relative h-40 w-40 shrink-0 rounded-full p-3.5 shadow-sm"
              style={{
                background: total > 0 ? `conic-gradient(${gradient})` : "var(--muted)",
              }}
              aria-hidden
            >
              <div
                className="absolute inset-[11px] rounded-full"
                style={{
                  background:
                    total > 0
                      ? `conic-gradient(${gradient})`
                      : "color-mix(in srgb, var(--foreground) 6%, transparent)",
                }}
              />
              <div className="absolute inset-[22px] grid place-items-center rounded-full bg-card shadow-inner">
                <div className="text-center">
                  <p className="text-2xl font-extrabold leading-none text-foreground">{total}</p>
                  <p className="mt-1 text-[11px] text-muted-foreground font-medium">Tài khoản</p>
                </div>
              </div>
            </div>

            <ul className="min-w-[210px] flex-1 space-y-2">
              {donut.map((d) => (
                <li
                  key={d.label}
                  className="flex items-center justify-between gap-2 rounded-lg p-1.5 transition-colors hover:bg-muted/40"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full shadow-sm"
                      style={{ background: d.color }}
                    />
                    <span className="text-xs font-semibold text-foreground truncate">
                      {d.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 text-right">
                    <span className="font-bold text-xs text-foreground">{d.count}</span>
                    <span className="text-[11px] text-muted-foreground">
                      ({d.pct.toFixed(1)}%)
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* Tier 2: Stacked Multi-Color Progress Bar & Account Health Mini Cards */}
          <div className="space-y-3 rounded-xl border border-border/80 bg-muted/20 p-3.5">
            {/* Multi-Color Stacked Bar */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[11px] font-medium text-muted-foreground">
                <span>Cơ cấu phân bổ vai trò</span>
                <span>100%</span>
              </div>
              <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted">
                {donut.map((d) => (
                  <div
                    key={d.label}
                    style={{
                      width: `${d.pct}%`,
                      background: d.color,
                    }}
                    title={`${d.label}: ${d.count} (${d.pct.toFixed(1)}%)`}
                    className="h-full transition-all duration-300"
                  />
                ))}
              </div>
            </div>

            {/* 3 Account Status Mini Cards */}
            <div className="grid grid-cols-3 gap-2 pt-1 text-center">
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2">
                <div className="flex items-center justify-center gap-1 text-[11px] font-semibold text-emerald-700 dark:text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" />
                  <span>Hoạt động</span>
                </div>
                <p className="mt-1 text-base font-bold text-emerald-600 dark:text-emerald-400">
                  {accounts.filter((a) => a.status === "active").length}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  {total > 0 ? Math.round((accounts.filter((a) => a.status === "active").length / total) * 100) : 0}% tổng số
                </p>
              </div>

              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2">
                <div className="flex items-center justify-center gap-1 text-[11px] font-semibold text-amber-700 dark:text-amber-400">
                  <Clock className="h-3 w-3" />
                  <span>Chờ kích hoạt</span>
                </div>
                <p className="mt-1 text-base font-bold text-amber-600 dark:text-amber-400">
                  {pending}
                </p>
                <p className="text-[10px] text-muted-foreground">Chưa xác thực</p>
              </div>

              <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-2">
                <div className="flex items-center justify-center gap-1 text-[11px] font-semibold text-rose-700 dark:text-rose-400">
                  <Lock className="h-3 w-3" />
                  <span>Đã khóa</span>
                </div>
                <p className="mt-1 text-base font-bold text-rose-600 dark:text-rose-400">
                  {locked}
                </p>
                <p className="text-[10px] text-muted-foreground">Tạm ngưng</p>
              </div>
            </div>
          </div>

          {/* Tier 3: Quick Role Jump Pills & Main Link */}
          <div className="space-y-2.5 pt-1">
            <div className="flex flex-wrap items-center justify-between gap-1.5">
              <Link
                href="/admin/accounts?group=patients"
                className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-primary/20 bg-primary/5 py-1.5 px-2 text-xs font-semibold text-primary transition hover:bg-primary/10"
              >
                <Users className="h-3 w-3" />
                <span>Bệnh nhân ({roleCounts.patient})</span>
              </Link>
              <Link
                href="/admin/accounts?group=doctors"
                className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-emerald-500/20 bg-emerald-500/5 py-1.5 px-2 text-xs font-semibold text-emerald-700 dark:text-emerald-400 transition hover:bg-emerald-500/10"
              >
                <Stethoscope className="h-3 w-3" />
                <span>Bác sĩ ({roleCounts.doctor})</span>
              </Link>
              <Link
                href="/admin/accounts?group=admins"
                className="flex flex-1 items-center justify-center gap-1 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800/60 py-1.5 px-2 text-xs font-semibold text-foreground transition hover:bg-muted"
              >
                <ShieldCheck className="h-3 w-3" />
                <span>Admin ({roleCounts.admin + roleCounts.superAdmin})</span>
              </Link>
            </div>

            <Link
              href="/admin/accounts"
              className="flex items-center justify-center gap-1.5 text-xs font-semibold text-primary hover:underline pt-1"
            >
              Quản lý tất cả tài khoản <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
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
            {loading ? (
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

    </div>
  );
}
