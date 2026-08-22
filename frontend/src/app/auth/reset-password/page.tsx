"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, Eye, EyeOff, Lock, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [isVerifying, setIsVerifying] = useState(true);

  useEffect(() => {
    const supabase = createClient();
    if (!supabase) {
      setError("Chưa cấu hình Supabase Auth");
      setIsVerifying(false);
      return;
    }

    (async () => {
      // 1. Doc query params va hash params tu link email Supabase
      const urlParams = new URLSearchParams(window.location.search);
      const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));

      // Kiem tra neu Supabase tra ve loi tu dong (vi du link het han / da dung)
      const urlError = urlParams.get("error_description") || hashParams.get("error_description");
      const urlErrorCode = urlParams.get("error_code") || hashParams.get("error_code");
      if (urlError || urlErrorCode) {
        if (urlErrorCode === "otp_expired" || urlError?.includes("expired")) {
          setError("Liên kết đặt lại mật khẩu đã hết hạn hoặc đã được sử dụng. Vui lòng yêu cầu liên kết mới.");
        } else {
          setError(urlError ? decodeURIComponent(urlError.replace(/\+/g, " ")) : "Liên kết đặt lại mật khẩu không hợp lệ.");
        }
        setIsVerifying(false);
        return;
      }

      const code = urlParams.get("code") || hashParams.get("code");
      const directToken = hashParams.get("access_token") || urlParams.get("access_token");
      const tokenHash =
        urlParams.get("token_hash") ||
        urlParams.get("token") ||
        hashParams.get("token_hash") ||
        hashParams.get("token");
      const type = (urlParams.get("type") || hashParams.get("type") || "recovery") as
        | "recovery"
        | "signup"
        | "email"
        | "invite";

      // 2. Neu co token_hash (OTP flow)
      if (tokenHash) {
        const { data, error: otpError } = await supabase.auth.verifyOtp({
          token_hash: tokenHash,
          type: type === "recovery" ? "recovery" : "email",
        });
        if (otpError) {
          console.warn("verifyOtp recovery error:", otpError);
        } else if (data.session?.access_token) {
          setToken(data.session.access_token);
          setIsVerifying(false);
          return;
        }
      }

      // 3. Neu co PKCE code
      if (code) {
        const { data, error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
        if (exchangeError) {
          console.warn("exchangeCodeForSession error:", exchangeError);
        } else if (data.session?.access_token) {
          setToken(data.session.access_token);
          setIsVerifying(false);
          return;
        }
      }

      // 4. Neu co access_token truc tiep tu hash (Implicit flow)
      if (directToken) {
        setToken(directToken);
        setIsVerifying(false);
        return;
      }

      // 5. Kiem tra session san co trong browser
      const {
        data: { session },
        error: sessionError,
      } = await supabase.auth.getSession();
      if (session?.access_token) {
        setToken(session.access_token);
      } else if (sessionError) {
        console.warn("getSession error:", sessionError);
      }
      setIsVerifying(false);
    })();

    // 6. Lang nghe su kien PASSWORD_RECOVERY tu Supabase client
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "PASSWORD_RECOVERY" || session?.access_token) {
        if (session?.access_token) {
          setToken(session.access_token);
        }
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (newPassword.length < 8) {
      setError("Mật khẩu mới phải có tối thiểu 8 ký tự");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Xác nhận mật khẩu không khớp");
      return;
    }

    setLoading(true);

    try {
      const supabase = createClient();
      if (!supabase) {
        throw new Error("Chưa cấu hình Supabase Auth");
      }

      let currentToken = token;

      // 1. Neu chua co token trong state, thu lay session tu Supabase client
      if (!currentToken) {
        const { data: { session } } = await supabase.auth.getSession();
        if (session?.access_token) {
          currentToken = session.access_token;
          setToken(session.access_token);
        }
      }

      // 2. Cap nhat mat khau truc tiep qua Supabase Browser Client
      const { data: updateData, error: updateError } = await supabase.auth.updateUser({
        password: newPassword,
      });

      if (updateError) {
        throw updateError;
      }

      // 3. Dong bo sang backend qua route handler /api/auth/reset-password
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(currentToken ? { Authorization: `Bearer ${currentToken}` } : {}),
        },
        body: JSON.stringify({
          new_password: newPassword,
          access_token: currentToken,
          email: updateData.user?.email,
          provider_account_id: updateData.user?.id,
        }),
      });

      const data = await res.json().catch(() => null);

      if (!res.ok) {
        throw new Error(data?.detail ?? "Đặt lại mật khẩu thất bại");
      }

      setSuccess(true);
      setTimeout(() => {
        router.push("/login");
      }, 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đặt lại mật khẩu thất bại");
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
          <h1 className="text-2xl font-bold tracking-tight">Đặt lại mật khẩu</h1>
          <p className="text-sm text-muted-foreground">
            Nhập mật khẩu mới an toàn cho tài khoản của bạn
          </p>
        </div>

        <section className="surface-card p-6 sm:p-8">
          {success ? (
            <div className="space-y-4 text-center">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <div className="space-y-2">
                <h3 className="text-base font-semibold">Đổi mật khẩu thành công!</h3>
                <p className="text-sm text-muted-foreground">
                  Mật khẩu của bạn đã được cập nhật. Hệ thống đang tự động chuyển về trang Đăng
                  nhập...
                </p>
              </div>
              <div className="pt-2">
                <Link
                  href="/login"
                  className="inline-flex w-full items-center justify-center rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
                >
                  Đăng nhập ngay
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="newPassword">Mật khẩu mới</Label>
                <div className="relative">
                  <Input
                    id="newPassword"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    placeholder="Tối thiểu 8 ký tự"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    className="absolute right-3 top-2.5 text-muted-foreground hover:text-foreground"
                    aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Xác nhận mật khẩu mới</Label>
                <div className="relative">
                  <Input
                    id="confirmPassword"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    placeholder="Nhập lại mật khẩu mới"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                  />
                  <Lock className="absolute right-3 top-2.5 h-4 w-4 text-muted-foreground" />
                </div>
              </div>

              {error && <p className="text-sm font-medium text-destructive">{error}</p>}

              <Button type="submit" className="w-full" size="lg" disabled={loading}>
                {loading ? "Đang cập nhật..." : "Cập nhật mật khẩu"}
              </Button>
            </form>
          )}
        </section>

        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <span>Bảo mật phiên đăng nhập an toàn</span>
        </div>
      </div>
    </main>
  );
}
