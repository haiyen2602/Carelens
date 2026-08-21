"use client";

import { CheckCircle2, Eye, EyeOff, Lock, User, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { CapyMascot } from "@/components/mascot/capy-mascot";

export function MobileLogin({
  email,
  password,
  onEmailChange,
  onPasswordChange,
  onSubmit,
  onClose,
  loading,
  error,
  justRegistered,
}: {
  email: string;
  password: string;
  onEmailChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
  onSubmit: (e: FormEvent) => void;
  onClose: () => void;
  loading: boolean;
  error: string;
  justRegistered: boolean;
}) {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background px-7 pb-10 pt-6">
      <button
        type="button"
        onClick={onClose}
        aria-label="Đóng"
        className="-ml-1 w-fit rounded-full p-1 text-foreground/80 transition-colors hover:bg-muted"
      >
        <X className="h-7 w-7" />
      </button>

      <div className="mt-6 flex justify-center">
        <CapyMascot variant="greet" size="lg" />
      </div>

      <form onSubmit={onSubmit} className="mt-10 space-y-4">
        <div className="flex items-center gap-3 rounded-2xl bg-muted px-5 py-4">
          <User className="h-6 w-6 shrink-0 text-muted-foreground" />
          <input
            type="text"
            autoComplete="email"
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
            placeholder="Số điện thoại/email đã đăng ký"
            className="min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground"
          />
        </div>

        <div className="flex items-center gap-3 rounded-2xl bg-muted px-5 py-4">
          <Lock className="h-6 w-6 shrink-0 text-muted-foreground" />
          <input
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            value={password}
            onChange={(e) => onPasswordChange(e.target.value)}
            placeholder="Nhập mật khẩu"
            className="min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground"
          />
          <button
            type="button"
            onClick={() => setShowPassword((s) => !s)}
            aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
            className="shrink-0 text-muted-foreground"
          >
            {showPassword ? <Eye className="h-6 w-6" /> : <EyeOff className="h-6 w-6" />}
          </button>
        </div>

        {justRegistered && (
          <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-medium text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            Đã đăng ký thành công. Vui lòng đăng nhập.
          </div>
        )}

        {error && <p className="text-sm font-medium text-destructive">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="mt-2 w-full rounded-2xl bg-primary py-4 text-lg font-bold text-primary-foreground shadow-sm transition-opacity disabled:opacity-60"
        >
          {loading ? "Đang đăng nhập..." : "Đăng nhập"}
        </button>
      </form>

      <a
        href="/auth/forgot-password"
        className="mt-7 text-center text-base font-semibold text-primary hover:underline"
      >
        Quên mật khẩu?
      </a>

      <p className="mt-8 text-center text-base text-foreground">
        Bạn chưa có tài khoản?{" "}
        <a href="/register" className="font-semibold text-primary hover:underline">
          Đăng ký ngay
        </a>
      </p>
    </div>
  );
}
