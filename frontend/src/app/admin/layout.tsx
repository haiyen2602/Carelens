"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  ChevronDown,
  ChevronLeft,
  FileClock,
  Flag,
  HelpCircle,
  Inbox,
  Home,
  LogOut,
  Menu,
  PillBottle,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  UserCog,
  Users,
  UserCircle,
  Users2,
} from "lucide-react";
import { useEffect, useState, Suspense, type ComponentType, type ReactNode } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth";

type SubNavItem = {
  to: string;
  label: string;
  groupParam?: string;
  icon?: ComponentType<{ className?: string }>;
};

type NavItem = {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: number;
  children?: SubNavItem[];
};

function AdminLayoutContent({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isLoginRoute = pathname === "/admin/login";
  const [collapsed, setCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [openSubmenus, setOpenSubmenus] = useState<Record<string, boolean>>({
    "/admin/accounts": true,
  });
  const { user, loading, logout } = useAuth();
  const authChecked = !loading && !!user && user.role === "admin";
  // Kiem tra that qua GET /health cua backend (khong can auth) - thay cho
  // badge "He thong on dinh" hardcode truoc day khong phan anh trang thai
  // thuc. null = dang kiem tra lan dau, sau do tu poll lai moi 60s.
  const [heThongOn, setHeThongOn] = useState<boolean | null>(null);
  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    let cancelled = false;
    const kiemTra = () => {
      fetch(`${apiBase}/health`)
        .then((res) => {
          if (!cancelled) setHeThongOn(res.ok);
        })
        .catch(() => {
          if (!cancelled) setHeThongOn(false);
        });
    };
    kiemTra();
    const timer = setInterval(kiemTra, 60_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (isLoginRoute || loading) return;
    if (!user || user.role !== "admin") {
      router.replace("/admin/login");
    }
  }, [isLoginRoute, loading, user, router]);

  const groups: { title: string; items: NavItem[] }[] = [
    {
      title: "Quản trị hệ thống",
      items: [
        { to: "/admin", label: "Trang chủ", icon: Home, exact: true },
        {
          to: "/admin/accounts",
          label: "Quản lý tài khoản",
          icon: Users2,
          children: [
            {
              to: "/admin/accounts?group=patients",
              label: "Bệnh nhân",
              groupParam: "patients",
              icon: Users,
            },
            {
              to: "/admin/accounts?group=doctors",
              label: "Bác sĩ",
              groupParam: "doctors",
              icon: UserCheck,
            },
            {
              to: "/admin/accounts?group=admins",
              label: "Admin",
              groupParam: "admins",
              icon: UserCog,
            },
          ],
        },
        { to: "/admin/medicines", label: "Dữ liệu thuốc (RAG)", icon: PillBottle },
        { to: "/admin/drug-requests", label: "Yêu cầu bổ sung thuốc", icon: Inbox },
        { to: "/admin/rag", label: "Giám sát RAG & AI", icon: Activity },
        { to: "/admin/tickets", label: "Báo cáo chatbot", icon: Flag },
        { to: "/admin/audit", label: "Log hệ thống", icon: FileClock },
      ],
    },
    {
      title: "Khác",
      items: [{ to: "/admin/settings", label: "Cài đặt", icon: Settings }],
    },
  ];

  const currentGroupParam =
    searchParams.get("group") ?? (pathname === "/admin/accounts" ? "patients" : "");

  const isActive = (item: NavItem) =>
    item.exact ? pathname === item.to : pathname.startsWith(item.to);

  const isSubActive = (sub: SubNavItem) => {
    if (pathname !== "/admin/accounts") return false;
    return sub.groupParam === currentGroupParam;
  };

  const toggleSubmenu = (to: string) => {
    setOpenSubmenus((prev) => ({
      ...prev,
      [to]: !prev[to],
    }));
  };

  const titleMap: Record<string, string> = {
    "/admin": "Trang chủ",
    "/admin/accounts": "Quản lý tài khoản",
    "/admin/medicines": "Dữ liệu thuốc (RAG)",
    "/admin/drug-requests": "Yêu cầu bổ sung thuốc",
    "/admin/tickets": "Báo cáo chatbot",
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
                const hasChildren = !!item.children && item.children.length > 0;
                const isSubOpen = openSubmenus[item.to] ?? active;

                return (
                  <div key={item.to} className="space-y-0.5">
                    {hasChildren && !collapsed ? (
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => toggleSubmenu(item.to)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            toggleSubmenu(item.to);
                          }
                        }}
                        title={item.label}
                        className={`relative flex cursor-pointer items-center justify-between border-l-[3px] py-2.5 pl-6 pr-4 text-sm font-medium transition-colors hover:bg-sidebar-accent/60 select-none ${
                          active
                            ? "border-l-primary bg-primary/5 font-semibold text-primary"
                            : "border-transparent text-sidebar-foreground/85"
                        }`}
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <Icon className="h-[18px] w-[18px] shrink-0" />
                          <span className="truncate">{item.label}</span>
                        </div>
                        <ChevronDown
                          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${
                            isSubOpen ? "rotate-180" : ""
                          }`}
                        />
                      </div>
                    ) : (
                      <Link
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
                    )}

                    {hasChildren && !collapsed && isSubOpen && (
                      <div className="relative my-0.5 space-y-0.5 pl-8 pr-3">
                        <div className="absolute left-[29px] top-1 bottom-1 w-[1px] bg-sidebar-border" />
                        {item.children?.map((sub) => {
                          const subActive = isSubActive(sub);
                          const SubIcon = sub.icon;
                          return (
                            <Link
                              key={sub.to}
                              href={sub.to}
                              onClick={() => setMenuOpen(false)}
                              className={`relative flex items-center gap-2.5 rounded-lg py-2 pl-3.5 pr-2.5 text-xs font-medium transition-colors ${
                                subActive
                                  ? "bg-primary/15 font-bold text-primary shadow-xs"
                                  : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-foreground"
                              }`}
                            >
                              <span
                                className={`h-1.5 w-1.5 shrink-0 rounded-full transition-colors ${
                                  subActive ? "bg-primary scale-125" : "bg-muted-foreground/40"
                                }`}
                              />
                              {SubIcon && <SubIcon className="h-3.5 w-3.5 shrink-0" />}
                              <span className="truncate">{sub.label}</span>
                            </Link>
                          );
                        })}
                      </div>
                    )}
                  </div>
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
            aria-label="Mở menu điều hướng"
          >
            <Menu className="h-5 w-5" />
          </button>
          <h2 className="min-w-0 flex-1 truncate text-lg font-bold sm:text-xl">{pageTitle}</h2>

          <span
            className={`hidden shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold sm:flex ${
              heThongOn === false
                ? "border-destructive/40 bg-destructive/10 text-destructive"
                : "border-success/40 bg-success/10 text-success"
            }`}
          >
            {heThongOn === false ? (
              <ShieldAlert className="h-3.5 w-3.5" />
            ) : (
              <ShieldCheck className="h-3.5 w-3.5" />
            )}
            {heThongOn === null
              ? "Đang kiểm tra…"
              : heThongOn
                ? "Hệ thống ổn định"
                : "Không kết nối được backend"}
          </span>
          <button
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted"
            aria-label="Trợ giúp"
          >
            <HelpCircle className="h-[18px] w-[18px]" />
          </button>

          <DropdownMenu>
            <DropdownMenuTrigger className="flex shrink-0 items-center gap-2 rounded-lg border-l border-border py-1 pl-3 outline-none hover:bg-muted">
              <span className="grid h-9 w-9 place-items-center rounded-full bg-accent text-sm font-bold text-accent-foreground">
                {(user?.full_name ?? "?").trim().charAt(0).toUpperCase()}
              </span>
              <div className="hidden min-w-0 text-left sm:block">
                <p className="truncate text-sm font-semibold leading-tight">
                  {user?.full_name ?? "…"}
                </p>
                <p className="text-xs text-muted-foreground">Quản trị viên</p>
              </div>
              <ChevronDown className="hidden h-4 w-4 shrink-0 text-muted-foreground sm:block" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel className="font-normal">
                <p className="truncate text-sm font-semibold leading-tight">
                  {user?.full_name ?? "…"}
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
                onClick={async () => {
                  await logout();
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

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="grid min-h-screen place-items-center bg-background">
          <p className="text-sm text-muted-foreground">Đang tải trang quản trị...</p>
        </div>
      }
    >
      <AdminLayoutContent>{children}</AdminLayoutContent>
    </Suspense>
  );
}
