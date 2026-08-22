"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu, Phone, Settings, X } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

export function PhoneShell({
  title,
  subtitle,
  children,
  tabs,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  tabs: { to: string; label: string; icon: ReactNode; exact?: boolean }[];
}) {
  const { role, logout: protoLogout, emergency, setEmergency } = useProto();
  const { logout: authLogout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const doLogout = async () => {
    setMenuOpen(false);
    await authLogout();
    protoLogout();
    router.push("/login");
  };

  return (
    <div className="h-dvh bg-secondary/60 px-0 py-0 sm:px-4 sm:py-8">
      <div className="relative mx-auto flex h-full w-full max-w-[430px] flex-col overflow-hidden bg-background sm:h-[min(860px,calc(100dvh-4rem))] sm:rounded-[2.25rem] sm:shadow-[var(--shadow-phone)]">
        <header className="brand-gradient grid shrink-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3 px-5 pb-5 pt-7 text-primary-foreground sm:rounded-t-[2.25rem]">
          <button
            aria-label="Menu"
            className="shrink-0 rounded-full bg-white/15 p-2"
            onClick={() => setMenuOpen(true)}
          >
            <Menu className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <p className="truncate text-lg font-extrabold">{title}</p>
            {subtitle && <p className="truncate text-sm opacity-80">{subtitle}</p>}
          </div>
        </header>

        <main className="min-h-0 min-w-0 flex-1 space-y-4 overflow-y-auto p-5">{children}</main>

        <nav
          className="grid shrink-0 border-t border-border bg-card sm:rounded-b-[2.25rem]"
          style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}
        >
          {tabs.map((t) => {
            const active = t.exact ? pathname === t.to : pathname.startsWith(t.to);
            return (
              <Link
                key={t.to}
                href={t.to}
                className={`flex flex-col items-center gap-1 py-3 text-[11px] font-medium ${
                  active ? "text-primary" : "text-muted-foreground"
                }`}
              >
                {t.icon}
                <span className="truncate">{t.label}</span>
              </Link>
            );
          })}
        </nav>

        {menuOpen && (
          <>
            <div
              className="absolute inset-0 z-40 bg-foreground/40"
              onClick={() => setMenuOpen(false)}
              aria-hidden="true"
            />
            <div className="absolute inset-y-0 left-0 z-50 flex w-[85%] max-w-[320px] flex-col bg-background shadow-2xl">
              <div className="brand-gradient flex items-center justify-between gap-3 px-5 pb-5 pt-7 text-primary-foreground">
                <div className="min-w-0">
                  <p className="truncate text-base font-extrabold">{title}</p>
                  {subtitle && <p className="truncate text-xs opacity-80">{subtitle}</p>}
                </div>
                <button
                  aria-label="Đóng menu"
                  className="shrink-0 rounded-full bg-white/15 p-2"
                  onClick={() => setMenuOpen(false)}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <nav className="flex-1 space-y-1 overflow-y-auto p-4">
                <Link
                  href={`/${role ?? "patient"}/settings`}
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium text-foreground hover:bg-muted"
                >
                  <Settings className="h-5 w-5 text-muted-foreground" />
                  Cài đặt
                </Link>
              </nav>

              <div className="shrink-0 border-t border-border p-4">
                <button
                  onClick={doLogout}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium text-destructive hover:bg-destructive/10"
                >
                  <LogOut className="h-5 w-5" />
                  Đăng xuất
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {emergency && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-destructive p-8 text-center text-destructive-foreground">
          <h2 className="text-3xl font-extrabold">Cảnh báo cấp cứu</h2>
          <p className="max-w-sm">
            Dấu hiệu nguy hiểm được phát hiện. Hãy gọi ngay 115 hoặc để người thân hỗ trợ bạn.
          </p>
          <a
            href="tel:115"
            className="flex items-center gap-2 rounded-full bg-white px-8 py-4 text-lg font-extrabold text-destructive"
          >
            <Phone className="h-5 w-5" /> Gọi 115
          </a>
          <Button
            variant="ghost"
            className="text-destructive-foreground"
            onClick={() => setEmergency(false)}
          >
            <X className="mr-1 h-4 w-4" /> Đóng overlay
          </Button>
        </div>
      )}
    </div>
  );
}
