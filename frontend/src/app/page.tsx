"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState } from "react";
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
  QrCode,
  Send,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useProto, type Role } from "@/lib/proto-store";

const roles: { role: Role; label: string; desc: string; icon: typeof Stethoscope; hint: string }[] =
  [
    {
      role: "doctor",
      label: "Bác sĩ",
      desc: "Dashboard, kê đơn, hàng đợi duyệt HITL, audit log",
      icon: Stethoscope,
      hint: "Giao diện desktop",
    },
    {
      role: "patient",
      label: "Bệnh nhân/Người thân",
      desc: "Nhắc uống thuốc, xác nhận, chụp ảnh, báo sức khỏe · theo dõi tuân thủ của người thân",
      icon: HeartPulse,
      hint: "Web mobile",
    },
  ];

const features = [
  { icon: Clock, title: "Nhắc đúng giờ", desc: "Không bỏ lỡ liều thuốc nào" },
  { icon: ShieldCheck, title: "Xác nhận minh bạch", desc: "Ghi nhận và xác minh từng liều uống" },
  { icon: Stethoscope, title: "Bác sĩ đồng hành", desc: "Bác sĩ duyệt và theo dõi mọi thay đổi" },
  { icon: BellRing, title: "Cảnh báo kịp thời", desc: "Thông báo ngay khi có dấu hiệu bất thường" },
];

export default function LoginPage() {
  const [step, setStep] = useState<"phone" | "otp" | "role">("phone");
  const [phone, setPhone] = useState("912 345 678");
  const [otp, setOtp] = useState("");
  const [idValue, setIdValue] = useState("");
  const [picked, setPicked] = useState<Role | null>(null);
  const { login } = useProto();
  const router = useRouter();

  const finish = (role: Role) => {
    login(role, phone);
    router.push(role === "doctor" ? "/doctor" : "/patient");
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
          {step === "phone" && (
            <div className="space-y-5">
              <div>
                <h2 className="text-xl font-bold">Chào mừng bạn trở lại 👋</h2>
                <p className="text-sm text-muted-foreground">
                  Đăng nhập để tiếp tục sử dụng CapyMedi
                </p>
              </div>
              <div className="border-t border-border pt-5">
                <h3 className="font-bold">Đăng nhập</h3>
                <p className="text-sm text-muted-foreground">Nhập số điện thoại để nhận mã OTP.</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone">Số điện thoại</Label>
                <div className="flex items-stretch overflow-hidden rounded-md border border-input bg-card">
                  <span className="flex shrink-0 items-center gap-1 border-r border-input px-3 text-sm text-muted-foreground">
                    🇻🇳 +84
                  </span>
                  <Input
                    id="phone"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="rounded-none border-0 shadow-none focus-visible:ring-0"
                  />
                </div>
              </div>
              <Button className="w-full" size="lg" onClick={() => setStep("otp")}>
                Gửi mã OTP <Send className="ml-1 h-4 w-4" />
              </Button>

              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" /> hoặc{" "}
                <span className="h-px flex-1 bg-border" />
              </div>

              <Button variant="outline" className="w-full">
                <QrCode className="mr-1 h-4 w-4" /> Đăng nhập bằng mã QR
              </Button>

              <div className="flex items-start gap-3 rounded-lg bg-muted p-3">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <p className="text-xs text-muted-foreground">
                  <span className="font-semibold text-foreground">Bảo mật &amp; an toàn</span> —
                  Thông tin của bạn được mã hóa và bảo vệ theo tiêu chuẩn bảo mật cao nhất.
                </p>
              </div>

              <p className="text-center text-xs text-muted-foreground">
                Chưa có tài khoản? Liên hệ quản trị hệ thống bệnh viện.
              </p>
            </div>
          )}

          {step === "otp" && (
            <div className="space-y-5">
              <div>
                <h2 className="text-lg font-bold">Xác thực OTP</h2>
                <p className="text-sm text-muted-foreground">
                  Mã demo: <span className="font-semibold text-foreground">123456</span> (nhập gì
                  cũng hợp lệ trong prototype).
                </p>
              </div>
              <Input
                inputMode="numeric"
                placeholder="______"
                className="text-center text-2xl tracking-[0.5em]"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
              />
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setStep("phone")}>
                  Quay lại
                </Button>
                <Button className="flex-1" onClick={() => setStep("role")}>
                  Xác thực
                </Button>
              </div>
            </div>
          )}

          {step === "role" && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-bold">Bạn là ai?</h2>
                <p className="text-sm text-muted-foreground">Rẽ vai để vào đúng luồng.</p>
              </div>
              <div className="space-y-3">
                {roles.map((r) => {
                  const Icon = r.icon;
                  const active = picked === r.role;
                  return (
                    <button
                      key={r.role}
                      onClick={() => setPicked(r.role)}
                      className={`flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-colors ${
                        active ? "border-primary bg-accent" : "border-border hover:bg-muted"
                      }`}
                    >
                      <span className="brand-gradient grid h-10 w-10 shrink-0 place-items-center rounded-lg text-primary-foreground">
                        <Icon className="h-5 w-5" />
                      </span>
                      <span className="min-w-0">
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold">{r.label}</span>
                          <span className="rounded bg-secondary px-1.5 py-0.5 text-[11px] font-medium text-secondary-foreground">
                            {r.hint}
                          </span>
                        </span>
                        <span className="mt-1 block text-sm text-muted-foreground">{r.desc}</span>
                      </span>
                    </button>
                  );
                })}
              </div>

              {picked && (
                <div className="space-y-2 rounded-xl bg-muted p-4">
                  <Label htmlFor="idv">
                    {picked === "doctor" ? "Nhập ID bác sĩ" : "Nhập ID bệnh nhân"}
                  </Label>
                  <Input
                    id="idv"
                    placeholder={picked === "doctor" ? "BS-0114" : "BN-2049"}
                    value={idValue}
                    onChange={(e) => setIdValue(e.target.value)}
                  />
                </div>
              )}

              <Button
                className="w-full"
                size="lg"
                disabled={!picked}
                onClick={() => picked && finish(picked)}
              >
                Vào hệ thống
              </Button>
            </div>
          )}
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
