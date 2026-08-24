"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  Bell,
  BellOff,
  BookText,
  ChevronLeft,
  FileClock,
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
import { HelpGuideButton } from "@/components/help-guide-button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { presentAlert } from "@/lib/alert-presentation";
import { useAuth } from "@/lib/auth";
import { useProto, type AlertLevel } from "@/lib/proto-store";

// Cham mau canh theo muc do - popover chi co cho cho mot dau hieu nho, dung
// vien mau hay nen mau o day se dam hon ca noi dung.
const alertDotTone: Record<AlertLevel, string> = {
  low: "bg-primary",
  mid: "bg-warning",
  high: "bg-destructive",
};

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: "alerts";
};

// Trang khong nam trong nav chinh (vao qua account menu) nhung van can tieu
// de rieng tren top bar thay vi mac dinh "Trang chu".
const EXTRA_TITLES: Record<string, string> = {
  "/doctor/profile": "Hồ sơ cá nhân",
  "/doctor/settings": "Cài đặt",
};

const groups: { title: string; items: NavItem[] }[] = [
  {
    title: "Bác sĩ",
    items: [
      { to: "/doctor", label: "Trang chủ", icon: Home, exact: true },
      { to: "/doctor/patients", label: "Quản lý bệnh nhân", icon: Users2 },
      { to: "/doctor/prescribe", label: "Kê đơn thuốc", icon: Pill },
      { to: "/doctor/drugs", label: "Tra cứu thuốc", icon: BookText },
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
  const { alerts, activity, patients, markAllActivityRead, logout: protoLogout } = useProto();
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
      router.replace("/login");
    }
  }, [loading, user, router]);

  const isActive = (item: NavItem) =>
    item.exact ? pathname === item.to : pathname.startsWith(item.to);

  const pageTitle =
    groups.flatMap((g) => g.items).find(isActive)?.label ?? EXTRA_TITLES[pathname] ?? "Trang chủ";

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
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted lg:hidden"
            onClick={() => setMenuOpen(true)}
            aria-label="Mở menu điều hướng"
          >
            <Menu className="h-5 w-5" />
          </button>
          <h2 className="min-w-0 flex-1 truncate text-lg font-bold sm:text-xl">{pageTitle}</h2>

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
            <PopoverContent align="end" className="w-[22rem] p-0">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <p className="text-sm font-bold">Thông báo</p>
                {alertCount > 0 && (
                  <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-bold text-destructive">
                    {alertCount} cảnh báo mới
                  </span>
                )}
              </div>
              <div className="max-h-96 overflow-y-auto">
                {newAlerts.length > 0 && (
                  <div className="border-b border-border pb-1">
                    <p className="px-4 pb-1 pt-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                      Cảnh báo
                    </p>
                    {newAlerts.slice(0, 5).map((a) => {
                      // presentAlert() doi `trigger` ky thuat (vd
                      // "dose_unconfirmed") thanh cau tieng Viet - truoc day
                      // popover nay in thang a.detail nen nguoi doc thay dung
                      // chuoi ma nguon. Cung ham ma trang Hop canh bao dung,
                      // hai cho khong con doc lech nhau.
                      const view = presentAlert(a, patients);
                      return (
                        <Link
                          key={a.id}
                          href="/doctor/alerts"
                          className="flex gap-3 px-4 py-2.5 hover:bg-muted"
                        >
                          <span
                            className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${alertDotTone[a.level]}`}
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-semibold">
                              {view.title}
                            </span>
                            <span className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                              <span className="truncate">{view.patientName}</span>
                              <span aria-hidden="true">·</span>
                              <span className="shrink-0">{a.at}</span>
                            </span>
                          </span>
                        </Link>
                      );
                    })}
                    <Link
                      href="/doctor/alerts"
                      className="block px-4 py-2.5 text-center text-xs font-semibold text-primary hover:bg-muted"
                    >
                      Xem tất cả cảnh báo →
                    </Link>
                  </div>
                )}

                <div className="pb-1">
                  <p className="px-4 pb-1 pt-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    Hoạt động
                  </p>
                  {activity.length === 0 && newAlerts.length === 0 && (
                    <div className="px-4 py-8 text-center">
                      <BellOff className="mx-auto h-8 w-8 text-muted-foreground/40" />
                      <p className="mt-2 text-sm text-muted-foreground">Chưa có thông báo nào.</p>
                    </div>
                  )}
                  {activity.length === 0 && newAlerts.length > 0 && (
                    <p className="px-4 py-3 text-sm text-muted-foreground">
                      Chưa có hoạt động nào.
                    </p>
                  )}
                  {activity.map((n) => (
                    <div key={n.id} className="flex gap-3 px-4 py-2.5">
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-muted-foreground/30" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">{n.title}</p>
                        {n.detail && (
                          <p className="truncate text-xs text-muted-foreground">{n.detail}</p>
                        )}
                        <p className="mt-0.5 text-[11px] text-muted-foreground">{n.at}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </PopoverContent>
          </Popover>
          <HelpGuideButton />

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
                  {(user?.full_name ?? "?").charAt(0)}
                </span>
                <div className="hidden min-w-0 text-left sm:block">
                  <p className="truncate text-sm font-semibold leading-tight">
                    {user?.full_name ?? "Đang tải…"}
                  </p>
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
                      router.push("/login");
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
