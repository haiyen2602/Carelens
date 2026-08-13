"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Mã xác minh không tồn tại hoặc đường dẫn không đúng.");
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/verify-email", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        const data = await res.json();
        if (!cancelled) {
          if (res.ok) {
            setStatus("success");
            setMessage("Địa chỉ email của bạn đã được xác minh thành công!");
          } else {
            setStatus("error");
            setMessage(data?.detail ?? "Mã xác minh không hợp lệ hoặc đã hết hạn.");
          }
        }
      } catch {
        if (!cancelled) {
          setStatus("error");
          setMessage("Không thể kết nối đến máy chủ. Vui lòng thử lại sau.");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary/5 via-background to-accent/20 px-6 py-12">
      <div className="mx-auto w-full max-w-md space-y-6 rounded-3xl border bg-card p-8 shadow-xl text-center">
        {status === "loading" && (
          <div className="space-y-4">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight">Đang xác minh email...</h1>
            <p className="text-sm text-muted-foreground">Vui lòng chờ trong giây lát.</p>
          </div>
        )}

        {status === "success" && (
          <div className="space-y-4">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-success/15 text-success">
              <CheckCircle2 className="h-8 w-8" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Xác minh thành công!</h1>
            <p className="text-sm text-muted-foreground">{message}</p>
            <div className="pt-2">
              <Link href="/">
                <Button className="w-full gap-2 h-11 text-base font-semibold">
                  <LogIn className="h-4 w-4" /> Đăng nhập ngay
                </Button>
              </Link>
            </div>
          </div>
        )}

        {status === "error" && (
          <div className="space-y-4">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-destructive/15 text-destructive">
              <AlertCircle className="h-8 w-8" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Xác minh thất bại</h1>
            <p className="text-sm text-destructive font-medium">{message}</p>
            <div className="pt-2 space-y-2">
              <Link href="/">
                <Button variant="outline" className="w-full gap-2 h-11">
                  Về trang đăng nhập
                </Button>
              </Link>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
