"use client";

import { KeyRound, Mail, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { listAccounts, type AccountRecord } from "@/lib/accounts";

export default function AdminProfilePage() {
  const { user } = useAuth();
  const [me, setMe] = useState<AccountRecord | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!user?.id) return;
    listAccounts()
      .then((accounts) => {
        const found = accounts.find((a) => a.id === user.id) ?? null;
        setMe(found);
        setName(found?.fullName ?? user.full_name);
        setEmail(found?.email ?? "");
      })
      .catch(() => undefined);
  }, [user]);

  const meta = me
    ? [
        ["Mã quản trị viên", me.id],
        ["Vai trò", "Quản trị hệ thống"],
        ["Ngày tạo tài khoản", me.createdAt],
        ["Trạng thái", me.status],
      ]
    : [];

  const save = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <section className="surface-card p-6">
          <div className="flex items-center gap-4">
            <span className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-accent text-xl font-bold text-accent-foreground">
              {(name || "?").charAt(0)}
            </span>
            <div className="min-w-0">
              <p className="truncate text-lg font-bold">{name || "…"}</p>
              <p className="text-sm text-muted-foreground">Quản trị hệ thống · {me?.id ?? "…"}</p>
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

          <div className="mt-4 flex items-start gap-3 rounded-xl border border-border bg-muted/60 p-4">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Hệ thống chưa có cơ chế phát hiện truy cập bất thường — mục này sẽ hiển thị cảnh báo
              thật khi tính năng đó được xây dựng.
            </p>
          </div>
        </section>

        <section className="surface-card p-6">
          <h2 className="text-lg font-bold">Cập nhật thông tin</h2>
          <p className="text-sm text-muted-foreground">
            Thay đổi tên hiển thị và email (demo — chưa có API cập nhật hồ sơ).
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
