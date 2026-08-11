"use client";

import { KeyRound, Mail, Phone, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ACCOUNTS } from "@/lib/admin-mock";

const me = ACCOUNTS.find((a) => a.id === "ADM-001")!;

const meta = [
  ["Mã quản trị viên", me.id],
  ["Vai trò", "Quản trị hệ thống"],
  ["Ngày tạo tài khoản", me.createdAt],
  ["Đăng nhập gần nhất", me.lastLogin],
];

export default function AdminProfilePage() {
  const [name, setName] = useState(me.name);
  const [email, setEmail] = useState(me.email);
  const [phone, setPhone] = useState(me.phone);
  const [saved, setSaved] = useState(false);

  const save = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Hồ sơ cá nhân</h1>
        <p className="text-sm text-muted-foreground">
          Thông tin tài khoản quản trị viên đang đăng nhập.
        </p>
      </header>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <section className="surface-card p-6">
          <div className="flex items-center gap-4">
            <span className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-accent text-xl font-bold text-accent-foreground">
              {name.charAt(0)}
            </span>
            <div className="min-w-0">
              <p className="truncate text-lg font-bold">{name}</p>
              <p className="text-sm text-muted-foreground">Quản trị hệ thống · {me.id}</p>
            </div>
          </div>

          <dl className="mt-6 grid gap-4 sm:grid-cols-2">
            {meta.map(([k, v]) => (
              <div key={k} className="rounded-xl bg-muted p-4">
                <dt className="text-xs font-semibold uppercase text-muted-foreground">{k}</dt>
                <dd className="mt-1 truncate font-semibold">{v}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-4 flex items-start gap-3 rounded-xl border border-success/40 bg-success/10 p-4">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-success" />
            <p className="text-sm text-success">
              Tài khoản đang hoạt động bình thường, chưa ghi nhận truy cập bất thường.
            </p>
          </div>
        </section>

        <section className="surface-card p-6">
          <h2 className="text-lg font-bold">Cập nhật thông tin</h2>
          <p className="text-sm text-muted-foreground">
            Thay đổi tên hiển thị và thông tin liên hệ (demo — chưa đồng bộ máy chủ).
          </p>

          <div className="mt-4 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Họ và tên</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <div className="flex items-center overflow-hidden rounded-md border border-input bg-card focus-within:border-primary">
                <span className="flex shrink-0 items-center px-3 text-muted-foreground">
                  <Mail className="h-4 w-4" />
                </span>
                <Input
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="rounded-none border-0 px-0 shadow-none focus-visible:ring-0"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="phone">Số điện thoại</Label>
              <div className="flex items-center overflow-hidden rounded-md border border-input bg-card focus-within:border-primary">
                <span className="flex shrink-0 items-center px-3 text-muted-foreground">
                  <Phone className="h-4 w-4" />
                </span>
                <Input
                  id="phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="rounded-none border-0 px-0 shadow-none focus-visible:ring-0"
                />
              </div>
            </div>

            <div className="flex items-center gap-3 pt-1">
              <Button onClick={save}>Lưu thay đổi</Button>
              {saved && <p className="text-sm font-semibold text-success">Đã lưu.</p>}
            </div>
          </div>

          <div className="mt-6 border-t border-border pt-5">
            <p className="flex items-center gap-2 text-sm font-semibold">
              <KeyRound className="h-4 w-4 text-muted-foreground" /> Bảo mật
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Đổi mật khẩu và quản lý xác thực 2 lớp trong{" "}
              <a href="/admin/settings" className="font-medium text-primary hover:underline">
                Cài đặt quản trị
              </a>
              .
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
