"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  Bell,
  ChevronLeft,
  FileClock,
  HelpCircle,
  Home,
  LayoutGrid,
  LogOut,
  Menu,
  Pill,
  Settings,
  UserCircle,
  Users,
  Users2,
} from "lucide-react";
import { useEffect, useRef, useState, type ComponentType, type ReactNode } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: "alerts";
};

const groups: { title: string; items: NavItem[] }[] = [
  {
    title: "Bác sĩ",
    items: [
      { to: "/doctor", label: "Trang chủ", icon: Home, exact: true },
      { to: "/doctor/patients", label: "Quản lý bệnh nhân", icon: Users2 },
      { to: "/doctor/prescribe", label: "Kê đơn thuốc", icon: Pill },
      { to: "/doctor/alerts", label: "Hộp cảnh báo", icon: Bell, badge: "alerts" },
      { to: "/doctor/family", label: "Danh sách người thân", icon: Users },
      { to: "/doctor/audit", label: "Lịch sử", icon: FileClock },
    ],
  },
  {
    title: "Báo cáo",
    items: [{ to: "/doctor/reports/adherence", label: "Tổng quan thông tin", icon: BarChart3 }],
  },
];

export default function DoctorLayout({ children }: { children: ReactNode }) {
  const { alerts, activity, markAllActivityRead, logout: protoLogout } = useProto();
  const { user, loading, logout: authLogout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement | null>(null);
  // Cho mot chut truoc khi dong khi roi chuot, huy neu con tro quay lai truoc
  // khi het gio - tranh dong ngay lap tuc khi chuot luot qua mep.
  const accountMenuCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const openAccountMenu = () => {
    if (accountMenuCloseTimer.current) clearTimeout(accountMenuCloseTimer.current);
    setAccountMenuOpen(true);
  };
  const scheduleCloseAccountMenu = () => {
    accountMenuCloseTimer.current = setTimeout(() => setAccountMenuOpen(false), 150);
  };
  useEffect(() => {
    return () => {
      if (accountMenuCloseTimer.current) clearTimeout(accountMenuCloseTimer.current);
    };
  }, []);
  useEffect(() => {
    if (!accountMenuOpen) return;
    const onClickOutside = (e: MouseEvent) => {
      if (accountMenuRef.current && !accountMenuRef.current.contains(e.target as Node)) {
        setAccountMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [accountMenuOpen]);
  const newAlerts = alerts.filter((a) => a.status === "new");
  const alertCount = newAlerts.length;
  const unreadActivity = activity.filter((a) => !a.read).length;
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
                const badge = item.badge === "alerts" ? alertCount : 0;
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
          <h2 className="min-w-0 flex-1 truncate text-lg font-bold sm:text-xl">Trang chủ</h2>

          <Popover onOpenChange={(open) => open && markAllActivityRead()}>
            <PopoverTrigger asChild>
              <button className="relative grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted">
                <Bell className="h-[18px] w-[18px]" />
                {alertCount + unreadActivity > 0 && (
                  <span className="absolute -right-0.5 -top-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
                    {alertCount + unreadActivity}
                  </span>
                )}
              </button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-80 p-0">
              <div className="border-b border-border px-4 py-3">
                <p className="text-sm font-bold">Thông báo</p>
              </div>
              <div className="max-h-96 overflow-y-auto">
                {newAlerts.length > 0 && (
                  <div className="border-b border-border">
                    <p className="px-4 pt-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                      Cảnh báo
                    </p>
                    {newAlerts.slice(0, 5).map((a) => (
                      <Link
                        key={a.id}
                        href="/doctor/alerts"
                        className="block px-4 py-2.5 hover:bg-muted"
                      >
                        <p className="truncate text-sm font-semibold">{a.title}</p>
                        <p className="truncate text-xs text-muted-foreground">{a.detail}</p>
                      </Link>
                    ))}
                    <Link
                      href="/doctor/alerts"
                      className="block px-4 py-2.5 text-center text-xs font-semibold text-primary hover:bg-muted"
                    >
                      Xem tất cả cảnh báo →
                    </Link>
                  </div>
                )}

                <div>
                  <p className="px-4 pt-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    Hoạt động
                  </p>
                  {activity.length === 0 && newAlerts.length === 0 && (
                    <p className="px-4 py-4 text-sm text-muted-foreground">
                      Chưa có thông báo nào.
                    </p>
                  )}
                  {activity.length === 0 && newAlerts.length > 0 && (
                    <p className="px-4 py-3 text-sm text-muted-foreground">
                      Chưa có hoạt động nào.
                    </p>
                  )}
                  {activity.map((n) => (
                    <div key={n.id} className="px-4 py-2.5">
                      <p className="truncate text-sm font-semibold">{n.title}</p>
                      {n.detail && (
                        <p className="truncate text-xs text-muted-foreground">{n.detail}</p>
                      )}
                      <p className="mt-0.5 text-[11px] text-muted-foreground">{n.at}</p>
                    </div>
                  ))}
                </div>
              </div>
            </PopoverContent>
          </Popover>
          <button className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted">
            <HelpCircle className="h-[18px] w-[18px]" />
          </button>

          <div className="shrink-0 border-l border-border pl-3">
            <div
              ref={accountMenuRef}
              className="relative w-56"
              onMouseEnter={openAccountMenu}
              onMouseLeave={scheduleCloseAccountMenu}
            >
              <button
                className="flex w-full items-center gap-2 rounded-lg py-1 pl-1 pr-2 outline-none hover:bg-muted"
                onClick={() => setAccountMenuOpen((v) => !v)}
              >
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-sm font-bold text-accent-foreground">
                  H
                </span>
                <div className="hidden min-w-0 text-left sm:block">
                  <p className="truncate text-sm font-semibold leading-tight">BS. Phạm Quốc Huy</p>
                  <p className="text-xs text-muted-foreground">Bác sĩ</p>
                </div>
              </button>

              {accountMenuOpen && (
                <div className="absolute left-0 top-full z-50 w-full rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md">
                  <Link
                    href="/doctor/profile"
                    onClick={() => setAccountMenuOpen(false)}
                    className="flex items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground"
                  >
                    <UserCircle className="h-4 w-4" /> Hồ sơ cá nhân
                  </Link>
                  <Link
                    href="/doctor/settings"
                    onClick={() => setAccountMenuOpen(false)}
                    className="flex items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground"
                  >
                    <Settings className="h-4 w-4" /> Cài đặt
                  </Link>
                  <div className="my-1 h-px bg-muted" />
                  <button
                    onClick={async () => {
                      await authLogout();
                      protoLogout();
                      router.push("/");
                    }}
                    className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm text-destructive hover:bg-accent"
                  >
                    <LogOut className="h-4 w-4" /> Đăng xuất
                  </button>
                </div>
              )}
            </div>
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
