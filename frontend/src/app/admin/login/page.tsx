"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Eye, EyeOff, Lock, ShieldCheck, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";

export default function AdminLoginPage() {
  const router = useRouter();
  const { user, loading: authLoading, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const redirectedRef = useRef(false);

  useEffect(() => {
    if (authLoading || !user || redirectedRef.current) return;
    if (user.role === "admin" || user.role === "super_admin") {
      redirectedRef.current = true;
      router.replace("/admin");
    }
  }, [user, authLoading, router]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("Vui lòng nhập đầy đủ tài khoản và mật khẩu.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const u = await login(username.trim(), password);
      if (u.role !== "admin" && u.role !== "super_admin") {
        setError("Tài khoản này không có quyền truy cập trang quản trị.");
        setLoading(false);
        return;
      }
      router.push("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại.");
      setLoading(false);
    }
  };

  if (authLoading || (user && (user.role === "admin" || user.role === "super_admin"))) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <p className="text-sm text-muted-foreground">Đang kiểm tra phiên đăng nhập...</p>
      </div>
    );
  }

  return (
    <main className="grid min-h-screen place-items-center bg-gradient-to-br from-secondary/70 via-background to-accent/40 px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <Image
            src="/logo-capymedi-v2.png"
            alt="CapyMedi"
            width={56}
            height={56}
            className="h-12 w-12"
            priority
          />
          <p className="mt-3 text-xl font-extrabold tracking-tight">CapyMedi</p>
          <p className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            Admin console — Quản trị hệ thống
          </p>
        </div>

        <section className="surface-card p-6 sm:p-8">
          <div className="mb-5">
            <h1 className="text-lg font-bold">Đăng nhập quản trị</h1>
            <p className="text-sm text-muted-foreground">
              Dành cho quản trị viên nội bộ/demo. Không dùng chung luồng OTP với bác sĩ và bệnh
              nhân.
            </p>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Email</Label>
              <div className="flex items-center overflow-hidden rounded-md border border-input bg-card focus-within:border-primary">
                <span className="flex shrink-0 items-center px-3 text-muted-foreground">
                  <User className="h-4 w-4" />
                </span>
                <Input
                  id="username"
                  type="email"
                  autoComplete="email"
                  placeholder="admin@capymedi.dev"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="rounded-none border-0 pl-0 shadow-none focus-visible:ring-0"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Mật khẩu</Label>
              <div className="flex items-center overflow-hidden rounded-md border border-input bg-card focus-within:border-primary">
                <span className="flex shrink-0 items-center px-3 text-muted-foreground">
                  <Lock className="h-4 w-4" />
                </span>
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="rounded-none border-0 px-0 shadow-none focus-visible:ring-0"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="flex shrink-0 items-center px-3 text-muted-foreground"
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && <p className="text-sm font-medium text-destructive">{error}</p>}

            <Button type="submit" className="w-full" size="lg" disabled={loading}>
              {loading ? "Đang đăng nhập..." : "Đăng nhập"}
            </Button>
          </form>

          <div className="mt-5 flex items-start gap-3 rounded-lg bg-muted p-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <p className="text-xs text-muted-foreground">
              <span className="font-semibold text-foreground">Chưa có tài khoản?</span> Tài khoản
              admin đầu tiên được tạo qua <code>scripts/create_admin.py</code> (xem TASK-010) —
              không có đăng ký công khai.
            </p>
          </div>
        </section>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          <a href="/login" className="font-medium text-primary hover:underline">
            ← Quay lại trang đăng nhập chính
          </a>
        </p>
      </div>
    </main>
  );
}
