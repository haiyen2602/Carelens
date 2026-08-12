"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronDown,
  ChevronLeft,
  FileClock,
  HelpCircle,
  Home,
  Link2,
  LogOut,
  Menu,
  PillBottle,
  Settings,
  ShieldCheck,
  UserCircle,
  Users2,
} from "lucide-react";
import { useEffect, useState, type ComponentType, type ReactNode } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ACCOUNTS } from "@/lib/admin-mock";
import { isAdminAuthed, setAdminAuthed } from "@/lib/admin-auth";

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: number;
};

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const isLoginRoute = pathname === "/admin/login";
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    if (isLoginRoute) return;
    if (!isAdminAuthed()) {
      router.replace("/admin/login");
      return;
    }
    setAuthChecked(true);
  }, [isLoginRoute, pathname, router]);

  const pendingAccounts = ACCOUNTS.filter((a) => a.status === "pending").length;

  const groups: { title: string; items: NavItem[] }[] = [
    {
      title: "Quản trị hệ thống",
      items: [
        { to: "/admin", label: "Dashboard", icon: Home, exact: true },
        { to: "/admin/accounts", label: "Quản lý tài khoản", icon: Users2, badge: pendingAccounts },
        { to: "/admin/links", label: "Liên kết bệnh nhân · bác sĩ · người thân", icon: Link2 },
        { to: "/admin/medicines", label: "Dữ liệu thuốc (RAG)", icon: PillBottle },
        { to: "/admin/audit", label: "Log hệ thống", icon: FileClock },
      ],
    },
    {
      title: "Khác",
      items: [{ to: "/admin/settings", label: "Cài đặt", icon: Settings }],
    },
  ];

  const isActive = (item: NavItem) =>
    item.exact ? pathname === item.to : pathname.startsWith(item.to);

  const titleMap: Record<string, string> = {
    "/admin": "Dashboard",
    "/admin/accounts": "Quản lý tài khoản",
    "/admin/links": "Liên kết bệnh nhân · bác sĩ · người thân",
    "/admin/medicines": "Dữ liệu thuốc (RAG)",
    "/admin/audit": "Log hệ thống",
    "/admin/profile": "Hồ sơ cá nhân",
    "/admin/settings": "Cài đặt",
  };
  const pageTitle = titleMap[pathname] ?? "Quản trị hệ thống";

  if (isLoginRoute) return <>{children}</>;

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
        {!collapsed && (
          <div className="min-w-0">
            <p className="truncate text-xl font-extrabold tracking-tight">CapyMedi</p>
            <p className="truncate text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Admin console
            </p>
          </div>
        )}
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
                        {!!item.badge && item.badge > 0 && (
                          <span className="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-warning px-1.5 text-[11px] font-bold text-warning-foreground">
                            {item.badge}
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
          collapsed ? "w-[76px]" : "w-[270px]"
        }`}
      >
        <div className="sticky top-0 h-screen">{sidebar}</div>
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-foreground/40" onClick={() => setMenuOpen(false)} />
          <div className="absolute left-0 top-0 h-full w-[270px] border-r border-sidebar-border">
            {sidebar}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-[70px] shrink-0 items-center gap-3 border-b border-border bg-card px-4 sm:px-6">
          <button
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted lg:hidden"
            onClick={() => setMenuOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <h2 className="min-w-0 flex-1 truncate text-lg font-bold sm:text-xl">{pageTitle}</h2>

          <span className="hidden shrink-0 items-center gap-1.5 rounded-full border border-success/40 bg-success/10 px-3 py-1 text-xs font-semibold text-success sm:flex">
            <ShieldCheck className="h-3.5 w-3.5" /> Hệ thống ổn định
          </span>
          <button className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted">
            <HelpCircle className="h-[18px] w-[18px]" />
          </button>

          <DropdownMenu>
            <DropdownMenuTrigger className="flex shrink-0 items-center gap-2 rounded-lg border-l border-border py-1 pl-3 outline-none hover:bg-muted">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-accent text-sm font-bold text-accent-foreground">
                Y
              </span>
              <div className="hidden min-w-0 text-left sm:block">
                <p className="truncate text-sm font-semibold leading-tight">Nguyễn Hải Yến</p>
                <p className="text-xs text-muted-foreground">Quản trị viên</p>
              </div>
              <ChevronDown className="hidden h-4 w-4 shrink-0 text-muted-foreground sm:block" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel className="font-normal">
                <p className="truncate text-sm font-semibold leading-tight">Nguyễn Hải Yến</p>
                <p className="truncate text-xs font-normal text-muted-foreground">
                  yen.nguyen@capymedi.dev
                </p>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => router.push("/admin/profile")}>
                <UserCircle /> Hồ sơ cá nhân
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => router.push("/admin/settings")}>
                <Settings /> Cài đặt
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => {
                  setAdminAuthed(false);
                  router.push("/admin/login");
                }}
              >
                <LogOut /> Đăng xuất
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        <div className="flex items-center gap-2 overflow-x-auto border-b border-border bg-card px-4 py-2 lg:hidden">
          {(groups[0]?.items ?? []).map((item) => {
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
        </div>

        <main className="min-w-0 flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
