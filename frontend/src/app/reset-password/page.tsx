"use client";

import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { AlertCircle, CheckCircle2, Lock, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ResetPasswordPage() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) {
      setError("Mã đặt lại mật khẩu không hợp lệ.");
      return;
    }
    if (password.length < 8) {
      setError("Mật khẩu mới phải có ít nhất 8 ký tự.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Mật khẩu xác nhận không khớp.");
      return;
    }

    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail ?? "Đặt lại mật khẩu thất bại.");
      }
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra.");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary/5 via-background to-accent/20 px-6 py-12">
        <div className="mx-auto w-full max-w-md space-y-6 rounded-3xl border bg-card p-8 shadow-xl text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-destructive/15 text-destructive">
            <AlertCircle className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">Đường dẫn không hợp lệ</h1>
          <p className="text-sm text-muted-foreground">
            Thiếu mã token xác thực để đặt lại mật khẩu. Vui lòng kiểm tra lại liên kết trong email của bạn.
          </p>
          <Link href="/forgot-password" className="block pt-2">
            <Button className="w-full h-11">Yêu cầu gửi lại email</Button>
          </Link>
        </div>
      </main>
    );
  }

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

        {!success ? (
          <>
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Lock className="h-7 w-7" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight">Đặt lại mật khẩu</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Tạo mật khẩu mới cho tài khoản của bạn
              </p>
            </div>

            <form onSubmit={submit} className="space-y-4">
              {error && (
                <div className="rounded-lg bg-destructive/15 p-3 text-sm font-medium text-destructive">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="password">Mật khẩu mới</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="password"
                    type="password"
                    placeholder="Tối thiểu 8 ký tự"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pl-9"
                    required
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirm_password">Xác nhận mật khẩu mới</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="confirm_password"
                    type="password"
                    placeholder="Nhập lại mật khẩu mới"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="pl-9"
                    required
                  />
                </div>
              </div>

              <Button type="submit" className="w-full h-11 text-base font-semibold" disabled={loading}>
                {loading ? "Đang cập nhật..." : "Cập nhật mật khẩu"}
              </Button>
            </form>
          </>
        ) : (
          <div className="text-center space-y-4">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-success/15 text-success">
              <CheckCircle2 className="h-7 w-7" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight">Đổi mật khẩu thành công!</h1>
            <p className="text-sm text-muted-foreground">
              Mật khẩu của bạn đã được cập nhật thành công. Vui lòng sử dụng mật khẩu mới để đăng nhập.
            </p>
            <div className="pt-2">
              <Link href="/">
                <Button className="w-full gap-2 h-11 text-base font-semibold">
                  <LogIn className="h-4 w-4" /> Đăng nhập ngay
                </Button>
              </Link>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
