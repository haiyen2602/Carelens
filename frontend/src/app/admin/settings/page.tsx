"use client";

import { ChangePasswordDialog } from "@/components/change-password-dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";


export default function AdminSettingsPage() {
  return (
    <div className="space-y-6">
      <section className="surface-card flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="min-w-0">
          <p className="text-sm font-semibold">Đổi mật khẩu tài khoản quản trị</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Áp dụng cho tài khoản quản trị viên đang đăng nhập. Cần nhập lại mật khẩu hiện tại.
          </p>
        </div>
        <ChangePasswordDialog />
      </section>
    </div>
  );
}
