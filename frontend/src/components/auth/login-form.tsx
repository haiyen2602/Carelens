"use client";

import Image from "next/image";
import { useState, type FormEvent } from "react";
import { CheckCircle2, Eye, EyeOff, Lock } from "lucide-react";

import { GoogleSignInButton } from "@/components/google-sign-in-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// Style dung chung cho cac o nhap cua trang dang nhap: cao 48px, bo goc 12px,
// focus ring mong theo mau primary (xem redesign login - muc 10).
const FIELD =
  "h-[52px] rounded-xl border-border bg-white px-4 text-sm shadow-none transition-[border-color,box-shadow] dark:bg-card " +
  "focus-visible:border-primary focus-visible:ring-4 focus-visible:ring-primary/10";

export function LoginForm({
  email,
  password,
  onEmailChange,
  onPasswordChange,
  onSubmit,
  loading,
  error,
  justRegistered,
  googleFailed,
}: {
  email: string;
  password: string;
  onEmailChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
  onSubmit: (e: FormEvent) => void;
  loading: boolean;
  error: string;
  justRegistered: boolean;
  googleFailed: boolean;
}) {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <section className="w-full max-w-[440px]">
      <Image
        src="/logo-capymedi-v2.png"
        alt="CapyMedi"
        width={200}
        height={200}
        className="h-[104px] w-[104px] shrink-0 [@media(max-height:820px)]:h-[84px] [@media(max-height:820px)]:w-[84px]"
        priority
      />

      <p className="mt-6 text-sm font-medium text-muted-foreground [@media(max-height:820px)]:mt-4">
        Chào mừng trở lại 👋
      </p>
      <h1 className="mt-1.5 text-[2.25rem] font-bold leading-[1.15] tracking-tight [@media(max-height:820px)]:text-[1.875rem]">
        Đăng nhập CapyMedi
      </h1>
      <p className="mt-2.5 text-[0.9375rem] text-muted-foreground">
        Theo dõi thuốc và chăm sóc người thân dễ dàng hơn.
      </p>

      <form
        onSubmit={onSubmit}
        className="mt-5 space-y-5 [@media(max-height:820px)]:mt-4 [@media(max-height:820px)]:space-y-4"
      >
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="example@email.com"
            className={FIELD}
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Mật khẩu</Label>
            <a
              href="/auth/forgot-password"
              className="text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm"
            >
              Quên mật khẩu?
            </a>
          </div>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              className={`${FIELD} pr-12`}
              value={password}
              onChange={(e) => onPasswordChange(e.target.value)}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
              aria-pressed={showPassword}
              className="absolute right-2 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {justRegistered && (
          <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            Đã đăng ký tài khoản thành công. Vui lòng đăng nhập.
          </div>
        )}

        {error && <p className="text-sm font-medium text-destructive">{error}</p>}

        {googleFailed && !error && (
          <p className="text-sm font-medium text-destructive">
            Đăng nhập bằng Google không hoàn tất. Vui lòng thử lại hoặc dùng email và mật khẩu.
          </p>
        )}

        <Button
          type="submit"
          className="h-[52px] w-full rounded-xl text-[0.9375rem] font-semibold shadow-sm"
          disabled={loading}
        >
          {loading ? "Đang đăng nhập..." : "Đăng nhập"}
        </Button>
      </form>

      <div className="my-6 flex items-center gap-4 [@media(max-height:820px)]:my-5">
        <span className="h-px flex-1 bg-border" />
        <span className="text-xs text-muted-foreground">hoặc</span>
        <span className="h-px flex-1 bg-border" />
      </div>

      <GoogleSignInButton
        label="Tiếp tục với Google"
        className="h-[52px] w-full rounded-xl text-[0.9375rem] font-medium"
      />

      <p className="mt-5 text-center text-sm text-muted-foreground">
        Chưa có tài khoản?{" "}
        <a
          href="/register"
          className="font-semibold text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-sm"
        >
          Đăng ký ngay
        </a>
      </p>

      <p className="mt-3.5 flex items-center justify-center gap-2 text-xs text-muted-foreground">
        <Lock className="h-3.5 w-3.5 shrink-0 text-primary/70" />
        Dữ liệu của bạn được mã hóa và bảo vệ an toàn.
      </p>
    </section>
  );
}
