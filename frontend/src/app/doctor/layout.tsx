"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bell,
  BookText,
  ChevronDown,
  ChevronLeft,
  ClipboardList,
  FileClock,
  Grid3x3,
  HelpCircle,
  Home,
  LayoutGrid,
  LogOut,
  Menu,
  MessagesSquare,
  Pill,
  Settings,
  UserCircle,
  Users,
  Users2,
} from "lucide-react";
import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: "queue" | "alerts";
};

const groups: { title: string; items: NavItem[] }[] = [
  {
    title: "Bác sĩ",
    items: [
      { to: "/doctor", label: "Dashboard", icon: Home, exact: true },
      { to: "/doctor/patients", label: "Quản lý bệnh nhân", icon: Users2 },
      { to: "/doctor/prescribe", label: "Kê đơn thuốc", icon: Pill },
      { to: "/doctor/queue", label: "Hàng đợi duyệt (HITL)", icon: ClipboardList, badge: "queue" },
      { to: "/doctor/alerts", label: "Hộp cảnh báo", icon: Bell, badge: "alerts" },
      { to: "/doctor/adherence", label: "Theo dõi tuân thủ", icon: Activity },
      { to: "/doctor/symptoms", label: "Nhật ký triệu chứng", icon: BookText },
      { to: "/doctor/family", label: "Family member list", icon: Users },
      { to: "/doctor/audit", label: "Audit log", icon: FileClock },
    ],
  },
  {
    title: "Báo cáo",
    items: [
      { to: "/doctor/reports/adherence", label: "Adherence tổng quan", icon: BarChart3 },
      { to: "/doctor/reports/heatmap", label: "Heatmap theo cữ uống", icon: Grid3x3 },
      { to: "/doctor/reports/ai-log", label: "Log hội thoại AI", icon: MessagesSquare },
    ],
  },
  {
    title: "Cài đặt",
    items: [
      { to: "/doctor/profile", label: "Hồ sơ cá nhân", icon: UserCircle },
      { to: "/doctor/settings", label: "Cài đặt", icon: Settings },
    ],
  },
];

export default function DoctorLayout({ children }: { children: ReactNode }) {
  const { alerts, prescriptions, logout: protoLogout } = useProto();
  const { user, loading, logout: authLogout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const pendingCount = prescriptions.filter((p) => p.status === "pending").length;
  const alertCount = alerts.filter((a) => a.status === "new").length;
  const authChecked = !loading && !!user && user.role === "doctor";

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "doctor") {
      router.replace("/");
    }
  }, [loading, user, router]);

  const isActive = (item: NavItem) =>
    item.exact ? pathname === item.to : pathname.startsWith(item.to);

  if (!authChecked) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <p className="text-sm text-muted-foreground">Đang kiểm tra đăng nhập...</p>
      </div>
    );
  }

  const sidebar = (
    <div className="flex h-full flex-col bg-sidebar">
      <div
        className={`flex h-[70px] shrink-0 items-center gap-2.5 border-b border-sidebar-border ${
          collapsed ? "justify-center px-2" : "px-6"
        }`}
      >
        <Image
          src="/logo-capymedi-v2.png"
          alt="CapyMedi"
          width={36}
          height={36}
          className="h-9 w-9 shrink-0"
          priority
        />
        {!collapsed && <p className="truncate text-xl font-extrabold tracking-tight">CapyMedi</p>}
      </div>

      <nav className="flex-1 overflow-y-auto py-4">
        {groups.map((g) => (
          <div key={g.title} className="mb-4">
            {!collapsed && (
              <p className="px-6 pb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                {g.title}
              </p>
            )}
            <div className="space-y-0.5">
              {g.items.map((item) => {
                const Icon = item.icon;
                const badge =
                  item.badge === "queue" ? pendingCount : item.badge === "alerts" ? alertCount : 0;
                const active = isActive(item);
                return (
                  <Link
                    key={item.to}
                    href={item.to}
                    onClick={() => setMenuOpen(false)}
                    title={item.label}
                    className={`relative flex items-center gap-3 border-l-[3px] py-2.5 text-sm font-medium transition-colors hover:bg-sidebar-accent/60 ${
                      collapsed ? "justify-center px-2" : "px-6"
                    } ${
                      active
                        ? "border-l-primary bg-primary/10 font-semibold text-primary hover:bg-primary/10"
                        : "border-transparent text-sidebar-foreground/85"
                    }`}
                  >
                    <Icon className="h-[18px] w-[18px] shrink-0" />
                    {!collapsed && (
                      <>
                        <span className="min-w-0 flex-1 truncate">{item.label}</span>
                        {badge > 0 && (
                          <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-destructive px-1.5 text-[11px] font-bold text-destructive-foreground">
                            {badge}
                          </span>
                        )}
                      </>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-sidebar-border p-4">
        <button
          onClick={() => setCollapsed((v) => !v)}
          className={`flex w-full items-center gap-2 rounded-xl border border-sidebar-border px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent/60 ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <ChevronLeft
            className={`h-4 w-4 transition-transform ${collapsed ? "rotate-180" : ""}`}
          />
          {!collapsed && <span>Thu gọn</span>}
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-background">
      <aside
        className={`hidden shrink-0 border-r border-sidebar-border lg:block ${
          collapsed ? "w-[76px]" : "w-[250px]"
        }`}
      >
        <div className="sticky top-0 h-screen">{sidebar}</div>
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-foreground/40" onClick={() => setMenuOpen(false)} />
          <div className="absolute left-0 top-0 h-full w-[260px] border-r border-sidebar-border">
            {sidebar}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-[70px] shrink-0 items-center gap-3 border-b border-border bg-card px-4 sm:px-6">
          <button
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted"
            onClick={() => setMenuOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <h2 className="min-w-0 flex-1 truncate text-lg font-bold sm:text-xl">Dashboard</h2>

          <Link
            href="/doctor/alerts"
            className="relative grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted"
          >
            <Bell className="h-[18px] w-[18px]" />
            <span className="absolute -right-0.5 -top-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
              {alertCount + pendingCount}
            </span>
          </Link>
          <button className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted">
            <HelpCircle className="h-[18px] w-[18px]" />
          </button>

          <div className="flex shrink-0 items-center gap-2 border-l border-border pl-3">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-accent text-sm font-bold text-accent-foreground">
              H
            </span>
            <div className="hidden min-w-0 sm:block">
              <p className="truncate text-sm font-semibold leading-tight">BS. Phạm Quốc Huy</p>
              <p className="text-xs text-muted-foreground">Bác sĩ</p>
            </div>
            <button
              title="Đăng xuất"
              onClick={async () => {
                await authLogout();
                protoLogout();
                router.push("/");
              }}
              className="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-muted"
            >
              <LogOut className="h-4 w-4" />
            </button>
            <ChevronDown className="hidden h-4 w-4 text-muted-foreground sm:block" />
          </div>
        </header>

        <div className="flex items-center gap-2 overflow-x-auto border-b border-border bg-card px-4 py-2 lg:hidden">
          {(groups[0]?.items ?? []).slice(0, 6).map((item) => {
            const active = isActive(item);
            return (
              <Link
                key={item.to}
                href={item.to}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium ${
                  active ? "bg-primary/10 font-semibold text-primary" : "text-muted-foreground"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          <LayoutGrid className="h-4 w-4 shrink-0 text-muted-foreground" />
        </div>

        <main className="min-w-0 flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
