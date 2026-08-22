"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { ArrowLeft, CheckCircle2, Mail, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient, isSupabaseConfigured } from "@/lib/supabase";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sentSuccess, setSentSuccess] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (!email.trim()) {
      setError("Vui lòng nhập địa chỉ email");
      return;
    }

    if (!isSupabaseConfigured) {
      setError("Hệ thống chưa cấu hình Supabase Auth. Vui lòng liên hệ quản trị viên.");
      return;
    }

    const supabase = createClient();
    if (!supabase) {
      setError("Không khởi tạo được Supabase client");
      return;
    }

    setLoading(true);

    try {
      const redirectTo = `${window.location.origin}/auth/reset-password`;
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo,
      });

      if (resetError) {
        throw resetError;
      }

      setSentSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gửi yêu cầu đặt lại mật khẩu thất bại");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="grid min-h-screen place-items-center bg-background px-4 py-8 sm:px-6">
      <div className="w-full max-w-md space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <Image
            src="/logo-capymedi-v2.png"
            alt="CapyMedi"
            width={48}
            height={48}
            className="h-12 w-12"
            priority
          />
          <h1 className="text-2xl font-bold tracking-tight">Quên mật khẩu</h1>
          <p className="text-sm text-muted-foreground">
            Nhập email tài khoản của bạn để nhận liên kết đặt lại mật khẩu
          </p>
        </div>

        <section className="surface-card p-6 sm:p-8">
          {sentSuccess ? (
            <div className="space-y-5 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <div className="space-y-2">
                <h3 className="text-base font-semibold">Đã gửi email khôi phục</h3>
                <p className="text-sm text-muted-foreground">
                  Chúng tôi đã gửi hướng dẫn đặt lại mật khẩu đến địa chỉ{" "}
                  <span className="font-semibold text-foreground">{email}</span>. Vui lòng kiểm tra
                  hộp thư (bao gồm cả thư rác/spam).
                </p>
              </div>
              <div className="pt-2">
                <Link
                  href="/login"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-background py-2.5 text-sm font-medium text-foreground hover:bg-muted"
                >
                  <ArrowLeft className="h-4 w-4" /> Quay lại Đăng nhập
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <div className="relative">
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    placeholder="name@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                  <Mail className="absolute right-3 top-2.5 h-4 w-4 text-muted-foreground" />
                </div>
              </div>

              {error && <p className="text-sm font-medium text-destructive">{error}</p>}

              <Button type="submit" className="w-full" size="lg" disabled={loading}>
                {loading ? "Đang gửi liên kết..." : "Gửi liên kết đặt lại"}
              </Button>

              <div className="text-center pt-2">
                <Link
                  href="/login"
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
                >
                  <ArrowLeft className="h-3.5 w-3.5" /> Quay lại đăng nhập
                </Link>
              </div>
            </form>
          )}
        </section>

        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <span>Bảo vệ bởi Supabase Auth &amp; CapyMedi Security</span>
        </div>
      </div>
    </main>
  );
}
