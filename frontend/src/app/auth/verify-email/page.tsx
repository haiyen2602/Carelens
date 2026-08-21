"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CheckCircle2, ShieldCheck, XCircle } from "lucide-react";

import { createClient } from "@/lib/supabase";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

export default function VerifyEmailPage() {
  const router = useRouter();
  const { updateSession } = useAuth();
  const { login: protoLogin, pushActivity } = useProto();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    (async () => {
      try {
        const supabase = createClient();
        let token: string | undefined;

        if (supabase) {
          const urlParams = new URLSearchParams(window.location.search);
          const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
          const code = urlParams.get("code") || hashParams.get("code");
          const directToken = hashParams.get("access_token") || urlParams.get("access_token");
          const tokenHash =
            urlParams.get("token_hash") ||
            urlParams.get("token") ||
            hashParams.get("token_hash") ||
            hashParams.get("token");
          const type = (urlParams.get("type") || hashParams.get("type") || "signup") as
            "signup" | "email" | "recovery" | "invite";

          // 1. Neu co token_hash tu Supabase verify link
          if (tokenHash) {
            const { data, error: otpError } = await supabase.auth.verifyOtp({
              token_hash: tokenHash,
              type: type === "signup" ? "signup" : "email",
            });
            if (otpError) {
              console.warn("verifyOtp error:", otpError);
            } else if (data.session?.access_token) {
              token = data.session.access_token;
            }
          }

          // 2. Neu co code PKCE
          if (!token && code) {
            const { data, error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
            if (exchangeError) {
              console.warn("exchangeCodeForSession error:", exchangeError);
            } else if (data.session?.access_token) {
              token = data.session.access_token;
            }
          }

          // 3. Neu co access_token truc tiep
          if (!token && directToken) {
            token = directToken;
          }

          // 4. Neu da co san session
          if (!token) {
            const {
              data: { session },
            } = await supabase.auth.getSession();
            if (session?.access_token) {
              token = session.access_token;
            }
          }
        }

        const res = await fetch("/api/auth/verify-email", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ access_token: token }),
        });

        const data = await res.json().catch(() => null);

        if (!res.ok) {
          throw new Error(data?.detail ?? "Xác minh email thất bại hoặc liên kết đã hết hạn.");
        }

        setSuccess(true);
        if (data.access_token && data.user) {
          updateSession(data.access_token, data.user);
          if (data.user.role === "patient" || data.user.role === "doctor") {
            protoLogin(data.user.role, data.user.full_name);
            pushActivity("Xác minh thành công", "Chào mừng bạn đã kích hoạt tài khoản!");
          }
        }

        setTimeout(() => {
          router.push("/");
        }, 3000);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Xác minh email thất bại.");
      } finally {
        setLoading(false);
      }
    })();
  }, [protoLogin, pushActivity, router, updateSession]);

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
          <h1 className="text-2xl font-bold tracking-tight">Xác minh tài khoản</h1>
        </div>

        <section className="surface-card p-6 sm:p-8">
          {loading ? (
            <div className="space-y-4 text-center">
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              <p className="text-sm text-muted-foreground">
                Đang xác thực liên kết email của bạn...
              </p>
            </div>
          ) : success ? (
            <div className="space-y-4 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <div className="space-y-2">
                <h3 className="text-base font-semibold text-foreground">
                  Kích hoạt tài khoản thành công!
                </h3>
                <p className="text-sm text-muted-foreground">
                  Email của bạn đã được xác minh. Hệ thống đang tự động chuyển về trang chính...
                </p>
              </div>
              <div className="pt-2">
                <Link
                  href="/"
                  className="inline-flex w-full items-center justify-center rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
                >
                  Đăng nhập ngay
                </Link>
              </div>
            </div>
          ) : (
            <div className="space-y-4 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-destructive/10 text-destructive">
                <XCircle className="h-6 w-6" />
              </div>
              <div className="space-y-2">
                <h3 className="text-base font-semibold text-destructive">
                  Xác minh không thành công
                </h3>
                <p className="text-sm text-muted-foreground">{error}</p>
              </div>
              <div className="pt-2">
                <Link
                  href="/"
                  className="inline-flex w-full items-center justify-center rounded-lg border border-border bg-background py-2.5 text-sm font-medium text-foreground hover:bg-muted"
                >
                  Quay lại trang chủ
                </Link>
              </div>
            </div>
          )}
        </section>

        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <span>Bảo mật hệ thống y tế CapyMedi</span>
        </div>
      </div>
    </main>
  );
}
