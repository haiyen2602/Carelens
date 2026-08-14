"use client";

import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import {
  Activity,
  Bell,
  BellRing,
  CheckCircle2,
  ChevronDown,
  Clock,
  Globe,
  HeartPulse,
  Pill,
  PillBottle,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

const features = [
  { icon: Clock, title: "Nhắc đúng giờ", desc: "Không bỏ lỡ liều thuốc nào" },
  { icon: ShieldCheck, title: "Xác nhận minh bạch", desc: "Ghi nhận và xác minh từng liều uống" },
  { icon: Stethoscope, title: "Bác sĩ đồng hành", desc: "Bác sĩ duyệt và theo dõi mọi thay đổi" },
  { icon: BellRing, title: "Cảnh báo kịp thời", desc: "Thông báo ngay khi có dấu hiệu bất thường" },
];

function LoginPageContent() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login: authLogin } = useAuth();
  const { login: protoLogin, pushActivity } = useProto();
  const router = useRouter();
  const searchParams = useSearchParams();
  const justRegistered = searchParams.get("registered") === "true";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError("Vui lòng nhập đầy đủ email và mật khẩu.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const user = await authLogin(email.trim(), password);
      if (user.role === "doctor" || user.role === "patient") {
        // Cau noi TAM: dashboard doctor/patient van la UI mock tinh (chua
        // doi theo tai khoan dang nhap that) - van can state role/phone cua
        // proto-store de cac UI hien co (PhoneShell header, banner...)
        // khong vo. KHONG PHAI nguon that cho danh tinh - danh tinh that la
        // useAuth().user (xem lib/auth.tsx).
        protoLogin(user.role, user.full_name);
        pushActivity("Đăng nhập thành công", `Chào mừng trở lại, ${user.full_name}.`);
        if (user.role === "patient" && user.profile_completed === false) {
          router.push("/onboarding/profile");
        } else {
          router.push(user.role === "doctor" ? "/doctor" : "/patient");
        }
      } else if (user.role === "admin") {
        router.push("/admin");
      } else {
        setError("Vai trò người thân/caregiver chưa được hỗ trợ trên giao diện web.");
        setLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại.");
      setLoading(false);
    }
  };

  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-2">
      <div className="relative overflow-hidden bg-gradient-to-br from-secondary/70 via-background to-accent/40 px-6 py-12 sm:px-12 lg:py-16">
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-accent/50 blur-3xl" />
        <div className="pointer-events-none absolute right-10 top-24 grid grid-cols-4 gap-2 opacity-40">
          {Array.from({ length: 16 }).map((_, i) => (
            <span key={i} className="h-1.5 w-1.5 rounded-full bg-primary" />
          ))}
        </div>

        <div className="relative mx-auto max-w-lg">
          <div className="flex items-center gap-3">
            <Image
              src="/logo-capymedi-v2.png"
              alt="CapyMedi"
              width={72}
              height={72}
              className="h-14 w-14 shrink-0 sm:h-16 sm:w-16"
              priority
            />
            <p className="text-2xl font-extrabold tracking-tight sm:text-3xl">CapyMedi</p>
          </div>

          <div className="mt-6 inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
            Nền tảng quản lý và nhắc uống thuốc thông minh
          </div>

          <h1 className="mt-4 text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl">
            Uống đúng thuốc, đúng giờ,
            <span className="block text-primary">luôn có bác sĩ đồng hành</span>
          </h1>
          <p className="mt-4 max-w-xl text-muted-foreground">
            CapyMedi nhắc bệnh nhân uống thuốc đúng lịch, ghi nhận xác nhận từng liều và giữ bác sĩ
            trong vòng lặp để duyệt mọi thay đổi phác đồ trước khi áp dụng.
          </p>

          <div className="relative mt-10 flex items-center justify-center gap-4 py-4">
            <div className="surface-card w-56 shrink-0 space-y-3 p-4">
              {[
                { time: "07:00", label: "Sáng", state: "pending" as const },
                { time: "13:00", label: "Trưa", state: "done" as const },
                { time: "20:00", label: "Tối", state: "upcoming" as const },
              ].map((row) => (
                <div key={row.time} className="flex items-center gap-3 text-sm">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
                    <Pill className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-mono font-semibold">{row.time}</span>
                    <span className="text-xs text-muted-foreground">{row.label}</span>
                  </span>
                  {row.state === "done" && (
                    <CheckCircle2 className="h-5 w-5 shrink-0 text-success" />
                  )}
                  {row.state === "upcoming" && (
                    <Bell className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                </div>
              ))}
            </div>

            <div className="surface-card w-36 shrink-0 space-y-2 p-4 text-center">
              <p className="text-xs font-semibold text-muted-foreground">Xác nhận đã uống</p>
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-success/15 text-success">
                <CheckCircle2 className="h-7 w-7" />
              </div>
              <p className="text-sm font-bold">09:30</p>
            </div>

            <span className="absolute -bottom-2 left-2 grid h-9 w-9 place-items-center rounded-full bg-primary/15 text-primary shadow-sm">
              <ShieldCheck className="h-4 w-4" />
            </span>
            <span className="absolute -top-3 left-10 grid h-9 w-9 -rotate-12 place-items-center rounded-full bg-card text-primary shadow-sm">
              <Pill className="h-4 w-4" />
            </span>
            <span className="absolute -right-3 top-6 grid h-9 w-9 place-items-center rounded-full bg-card text-primary shadow-sm">
              <PillBottle className="h-4 w-4" />
            </span>
            <span className="absolute -bottom-3 right-10 grid h-9 w-9 place-items-center rounded-full bg-card text-destructive shadow-sm">
              <Activity className="h-4 w-4" />
            </span>
          </div>

          <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {features.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="text-left">
                  <span className="grid h-10 w-10 place-items-center rounded-lg bg-accent text-accent-foreground">
                    <Icon className="h-5 w-5" />
                  </span>
                  <p className="mt-2 text-sm font-semibold">{f.title}</p>
                  <p className="text-xs text-muted-foreground">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="relative flex flex-col items-center justify-center gap-8 px-6 py-12 sm:px-12">
        <button className="absolute right-6 top-6 inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground">
          <Globe className="h-3.5 w-3.5" /> Tiếng Việt <ChevronDown className="h-3.5 w-3.5" />
        </button>

        <section className="surface-card w-full max-w-md p-6 sm:p-8">
          <div className="space-y-5">
            <div>
              <h2 className="text-xl font-bold">Chào mừng bạn trở lại 👋</h2>
              <p className="text-sm text-muted-foreground">
                Đăng nhập để tiếp tục sử dụng CapyMedi
              </p>
            </div>
            <form onSubmit={submit} className="space-y-4 border-t border-border pt-5">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Mật khẩu</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              {justRegistered && (
                <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-sm font-medium text-emerald-700 dark:bg-emerald-950/30 dark:border-emerald-800 dark:text-emerald-400">
                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                  Đã đăng ký tài khoản thành công. Vui lòng đăng nhập.
                </div>
              )}

              {error && <p className="text-sm font-medium text-destructive">{error}</p>}

              <Button type="submit" className="w-full" size="lg" disabled={loading}>
                {loading ? "Đang đăng nhập..." : "Đăng nhập"}
              </Button>
            </form>

            <div className="flex items-start gap-3 rounded-lg bg-muted p-3">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
              <p className="text-xs text-muted-foreground">
                <span className="font-semibold text-foreground">Bảo mật &amp; an toàn</span> — Thông
                tin của bạn được mã hóa và bảo vệ theo tiêu chuẩn bảo mật cao nhất.
              </p>
            </div>

            <p className="text-center text-sm text-muted-foreground">
              Chưa có tài khoản?{" "}
              <a href="/register" className="font-semibold text-primary hover:underline">
                Đăng ký ngay
              </a>
            </p>
          </div>
        </section>

        <p className="text-center text-xs text-muted-foreground">
          © {new Date().getFullYear()} CapyMedi. Bảo lưu mọi quyền.
          {" · "}
          <a href="/admin" className="font-medium text-primary hover:underline">
            Quản trị hệ thống
          </a>
        </p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="grid min-h-screen place-items-center bg-background"><p className="text-sm text-muted-foreground">Đang tải...</p></div>}>
      <LoginPageContent />
    </Suspense>
  );
}
