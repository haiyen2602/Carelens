"use client";

import { ChangePasswordDialog } from "@/components/change-password-dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

const options = [
  {
    id: "opt-2fa",
    title: "Bắt buộc xác thực 2 lớp cho bác sĩ & quản trị viên",
    desc: "Yêu cầu OTP mỗi lần đăng nhập vào giao diện web desktop.",
    checked: true,
  },
  {
    id: "opt-lock",
    title: "Tự động khoá tài khoản sau 5 lần đăng nhập sai",
    desc: "Áp dụng cho toàn bộ vai trò, admin có thể mở khoá thủ công.",
    checked: true,
  },
  {
    id: "opt-audit",
    title: "Gửi cảnh báo khi có thao tác nhạy cảm trên audit log",
    desc: "Thông báo tới toàn bộ quản trị viên khi có truy cập bất thường.",
    checked: false,
  },
];

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

      <p className="rounded-lg bg-muted/60 px-4 py-2.5 text-xs text-muted-foreground">
        Các thiết lập dưới đây hiện chỉ đổi trên màn hình này, chưa được lưu vào hệ thống — sẽ hoạt
        động thật khi có API tương ứng.
      </p>
      <div className="surface-card divide-y divide-border">
        {options.map((o) => (
          <div key={o.id} className="flex items-center justify-between gap-4 p-5">
            <div className="min-w-0">
              <Label htmlFor={o.id} className="text-sm font-semibold">
                {o.title}
              </Label>
              <p className="mt-1 text-sm text-muted-foreground">{o.desc}</p>
            </div>
            <Switch id={o.id} defaultChecked={o.checked} />
          </div>
        ))}
      </div>
    </div>
  );
}
