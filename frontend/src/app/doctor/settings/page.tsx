"use client";

import { useState } from "react";
import { ChangePasswordDialog } from "@/components/change-password-dialog";
import { Switch } from "@/components/ui/switch";

const options = [
  ["Nhận cảnh báo nghiêm trọng qua SMS", true],
  ["Tự động đẩy cảnh báo bỏ liều sau 3 lần nhắc", true],
  ["Cho phép AI đề xuất đổi giờ uống", true],
  ["Nhận báo cáo tuân thủ hằng tuần qua email", false],
] as const;

export default function SettingsPage() {
  const [state, setState] = useState<boolean[]>(options.map((o) => o[1]));
  return (
    <div className="space-y-5">
      <p className="rounded-lg bg-muted/60 px-4 py-2.5 text-xs text-muted-foreground">
        Các tuỳ chọn dưới đây hiện chỉ đổi trên màn hình này, chưa được lưu vào hệ thống — sẽ hoạt
        động thật khi có API tương ứng.
      </p>
      <div className="surface-card divide-y divide-border">
        {options.map(([label], i) => (
          <div key={label} className="flex items-center justify-between gap-4 p-5">
            <p className="min-w-0 text-sm font-medium">{label}</p>
            <Switch
              aria-label={label}
              checked={state[i] ?? false}
              onCheckedChange={(v) => setState((s) => s.map((x, j) => (j === i ? v : x)))}
            />
          </div>
        ))}
      </div>

      <section className="surface-card flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="min-w-0">
          <h2 className="text-sm font-bold uppercase text-muted-foreground">Bảo mật</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Đổi mật khẩu đăng nhập của tài khoản bác sĩ đang dùng.
          </p>
        </div>
        <ChangePasswordDialog />
      </section>
    </div>
  );
}
