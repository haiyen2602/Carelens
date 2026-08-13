"use client";

import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ArrowLeft, CheckCircle2, MailCheck, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function VerifyNoticePage() {
  return (
    <Suspense fallback={null}>
      <VerifyNoticeContent />
    </Suspense>
  );
}

function VerifyNoticeContent() {
  const searchParams = useSearchParams();
  const email = searchParams.get("email") ?? "email của bạn";

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const handleResend = async () => {
    if (!email || email === "email của bạn") return;
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const res = await fetch("/api/auth/resend-verification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail ?? "Gửi lại thất bại");
      }
      setMessage("Đã gửi lại email xác minh thành công! Vui lòng kiểm tra lại hộp thư.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary/5 via-background to-accent/20 px-6 py-12">
      <div className="mx-auto w-full max-w-md space-y-6 rounded-3xl border bg-card p-8 shadow-xl text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <MailCheck className="h-8 w-8" />
        </div>

        <div>
          <h1 className="text-2xl font-bold tracking-tight">Kiểm tra hộp thư của bạn</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Chúng tôi đã gửi đường dẫn xác minh đến địa chỉ:
          </p>
          <p className="mt-1 font-semibold text-foreground break-all">{email}</p>
        </div>

        <div className="rounded-xl bg-muted/60 p-4 text-xs text-muted-foreground text-left space-y-2">
          <div className="flex items-center gap-2 font-medium text-foreground">
            <CheckCircle2 className="h-4 w-4 text-primary" />
            <span>Hướng dẫn xác minh:</span>
          </div>
          <ol className="list-decimal list-inside space-y-1 pl-1">
            <li>Mở thư điện tử vừa nhận từ <strong>CapyMedi</strong>.</li>
            <li>Nhấp vào nút hoặc đường dẫn xác minh.</li>
            <li>Sau khi xác minh thành công, bạn có thể bắt đầu sử dụng đầy đủ dịch vụ.</li>
          </ol>
        </div>

        {message && (
          <div className="rounded-lg bg-success/15 p-3 text-sm font-medium text-success">
            {message}
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-destructive/15 p-3 text-sm font-medium text-destructive">
            {error}
          </div>
        )}

        <div className="space-y-3 pt-2">
          <Button
            variant="outline"
            className="w-full gap-2 h-11"
            onClick={handleResend}
            disabled={loading}
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            {loading ? "Đang gửi..." : "Gửi lại email xác minh"}
          </Button>

          <Link href="/" className="block">
            <Button variant="ghost" className="w-full gap-2 text-muted-foreground">
              <ArrowLeft className="h-4 w-4" /> Về trang đăng nhập
            </Button>
          </Link>
        </div>
      </div>
    </main>
  );
}
