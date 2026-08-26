"use client";

import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type FormEvent } from "react";
import { ChevronDown, Globe, Monitor, Smartphone } from "lucide-react";
import { toast } from "sonner";
import { HeroPanel } from "@/components/auth/hero-panel";
import { MobileLogin } from "@/components/auth/mobile-login";
import { LoginForm } from "@/components/auth/login-form";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

function LoginPageContent() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mobileView, setMobileView] = useState(false);
  const { user, loading: authLoading, login: authLogin } = useAuth();
  const { login: protoLogin, pushActivity } = useProto();
  const router = useRouter();
  const searchParams = useSearchParams();
  const justRegistered = searchParams.get("registered") === "true";
  // Luong Google that bai SAU khi da roi khoi trang (nguoi dung bam Huy o
  // Google, sai cau hinh OAuth...) -> tra ve kem ?error=google
  const googleFailed = searchParams.get("error") === "google";
  const redirectedRef = useRef(false);

  useEffect(() => {
    if (authLoading || !user || redirectedRef.current) return;
    if (user.role === "doctor" || user.role === "patient") {
      redirectedRef.current = true;
      if (user.role === "doctor") {
        router.replace("/doctor");
      } else if (user.role === "patient") {
        router.replace(user.profile_completed === false ? "/onboarding/profile" : "/patient");
      }
    } else if (user.role === "admin" || user.role === "super_admin") {
      redirectedRef.current = true;
      router.replace("/admin");
    }
  }, [user, authLoading, router]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError("Vui lòng nhập đầy đủ email và mật khẩu.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const u = await authLogin(email.trim(), password);
      if (u.role === "doctor" || u.role === "patient") {
        // Cau noi TAM: dashboard doctor/patient van la UI mock tinh (chua
        // doi theo tai khoan dang nhap that) - van can state role/phone cua
        // proto-store de cac UI hien co (PhoneShell header, banner...)
        // khong vo. KHONG PHAI nguon that cho danh tinh - danh tinh that la
        // useAuth().user (xem lib/auth.tsx).
        protoLogin(u.role, u.full_name);
        pushActivity("Đăng nhập thành công", `Chào mừng trở lại, ${u.full_name}.`);
        if (u.role === "patient" && u.profile_completed === false) {
          router.push("/onboarding/profile");
        } else {
          router.push(u.role === "doctor" ? "/doctor" : "/patient");
        }
      } else if (u.role === "admin" || u.role === "super_admin") {
        setError("Tài khoản quản trị vui lòng đăng nhập tại Cổng quản trị hệ thống (/admin/login).");
        setLoading(false);
      } else {
        setError("Vai trò người thân/caregiver chưa được hỗ trợ trên giao diện web.");
        setLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại.");
      setLoading(false);
    }
  };

  if (authLoading || user) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <Image
            src="/logo-capymedi-v2.png"
            alt="CapyMedi"
            width={48}
            height={48}
            className="h-12 w-12 animate-pulse"
            priority
          />
          <p className="text-sm font-medium text-muted-foreground">
            {user ? "Đang chuyển hướng..." : "Đang kiểm tra phiên đăng nhập..."}
          </p>
        </div>
      </div>
    );
  }

  if (mobileView) {
    return (
      <main className="h-dvh bg-secondary/60 px-0 py-0 sm:px-4 sm:py-8">
        <button
          onClick={() => setMobileView(false)}
          className="absolute right-6 top-6 z-10 inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground shadow-sm"
        >
          <Monitor className="h-3.5 w-3.5" /> Xem bản desktop
        </button>

        <div className="relative mx-auto flex h-full w-full max-w-[430px] flex-col overflow-hidden bg-background sm:h-[min(860px,calc(100dvh-4rem))] sm:rounded-[2.25rem] sm:shadow-[var(--shadow-phone)]">
          <MobileLogin
            email={email}
            password={password}
            onEmailChange={setEmail}
            onPasswordChange={setPassword}
            onSubmit={submit}
            onClose={() => setMobileView(false)}
            loading={loading}
            error={error}
            justRegistered={justRegistered}
          />
        </div>
      </main>
    );
  }

  return (
    <main className="relative grid min-h-screen bg-background lg:grid-cols-[minmax(520px,44%)_1fr]">
      {/* Control phu (ngon ngu, xem truoc mobile) - top-right cua ca layout,
          do uu tien thi giac thap so voi form dang nhap. */}
      <div className="absolute right-6 top-6 z-20 flex items-center gap-2">
        <div className="inline-flex h-[30px] items-center gap-2 rounded-lg border border-border/70 bg-card/70 px-2.5 shadow-sm">
          <Monitor
            className={`h-3.5 w-3.5 ${mobileView ? "text-muted-foreground" : "text-primary"}`}
            aria-hidden
          />
          <Switch
            checked={mobileView}
            onCheckedChange={setMobileView}
            aria-label="Xem trước giao diện mobile"
            title={mobileView ? "Đang xem bản mobile" : "Đang xem bản desktop"}
          />
          <Smartphone
            className={`h-3.5 w-3.5 ${mobileView ? "text-primary" : "text-muted-foreground"}`}
            aria-hidden
          />
        </div>
        <button
          type="button"
          onClick={() => toast("Đa ngôn ngữ đang được phát triển")}
          className="inline-flex h-[30px] items-center gap-1.5 rounded-lg border border-border/70 bg-card/70 px-2.5 text-xs font-medium text-muted-foreground shadow-sm transition-colors hover:bg-card hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Globe className="h-3.5 w-3.5" /> Tiếng Việt <ChevronDown className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Cot trai: logo + form dang nhap */}
      <div className="flex flex-col px-8 pb-8 pt-[clamp(1.5rem,4vh,3rem)] xl:px-14">
        <div className="flex flex-1 items-center justify-center">
          <LoginForm
            email={email}
            password={password}
            onEmailChange={setEmail}
            onPasswordChange={setPassword}
            onSubmit={submit}
            loading={loading}
            error={error}
            justRegistered={justRegistered}
            googleFailed={googleFailed}
          />
        </div>

        <footer className="mx-auto w-full max-w-[440px] pt-8 text-xs text-muted-foreground">
          © {new Date().getFullYear()} CapyMedi. Bảo lưu mọi quyền.
          {" · "}
          <a
            href="/admin/login"
            className="underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
          >
            Quản trị hệ thống
          </a>
        </footer>
      </div>

      {/* Cot phai: mascot la hero visual chinh */}
      <HeroPanel />
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="grid min-h-screen place-items-center bg-background">
          <p className="text-sm text-muted-foreground">Đang tải...</p>
        </div>
      }
    >
      <LoginPageContent />
    </Suspense>
  );
}
