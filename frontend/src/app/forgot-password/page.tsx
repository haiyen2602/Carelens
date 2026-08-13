"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { ArrowLeft, CheckCircle2, KeyRound, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setError("Vui lòng nhập địa chỉ email.");
      return;
    }
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail ?? "Gửi yêu cầu thất bại.");
      }
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary/5 via-background to-accent/20 px-6 py-12">
      <div className="mx-auto w-full max-w-md space-y-6 rounded-3xl border bg-card p-8 shadow-xl">
        <div className="flex items-center gap-3 justify-center mb-2">
          <Image
            src="/logo-capymedi-v2.png"
            alt="CapyMedi"
            width={56}
            height={56}
            className="h-12 w-12 shrink-0"
            priority
          />
          <span className="text-2xl font-extrabold tracking-tight">CapyMedi</span>
        </div>

        {!submitted ? (
          <>
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <KeyRound className="h-7 w-7" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight">Quên mật khẩu?</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Nhập địa chỉ email đăng ký của bạn. Chúng tôi sẽ gửi hướng dẫn đặt lại mật khẩu.
              </p>
            </div>

            <form onSubmit={submit} className="space-y-4">
              {error && (
                <div className="rounded-lg bg-destructive/15 p-3 text-sm font-medium text-destructive">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">Email tài khoản</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    placeholder="name@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="pl-9"
                    required
                  />
                </div>
              </div>

              <Button type="submit" className="w-full h-11 text-base font-semibold" disabled={loading}>
                {loading ? "Đang gửi yêu cầu..." : "Gửi hướng dẫn qua Email"}
              </Button>
            </form>
          </>
        ) : (
          <div className="text-center space-y-4">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-success/15 text-success">
              <CheckCircle2 className="h-7 w-7" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight">Đã gửi hướng dẫn!</h1>
            <p className="text-sm text-muted-foreground">
              Nếu email <strong className="text-foreground">{email}</strong> tồn tại trong hệ thống, chúng tôi đã gửi đường dẫn đặt lại mật khẩu.
            </p>
            <div className="rounded-xl bg-muted p-4 text-xs text-muted-foreground text-left">
              Lưu ý: Đường dẫn đặt lại mật khẩu có hiệu lực trong vòng <strong>1 giờ</strong>. Vui lòng kiểm tra kỹ cả thư mục Spams (Rác) nếu không tìm thấy trong Hộp thư đến.
            </div>
          </div>
        )}

        <div className="pt-2 text-center">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-primary transition-colors"
          >
            <ArrowLeft className="h-4 w-4" /> Quay lại Đăng nhập
          </Link>
        </div>
      </div>
    </main>
  );
}
