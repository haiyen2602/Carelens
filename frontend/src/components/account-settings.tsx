"use client";

import { useState } from "react";
import { Bell, ChevronRight, Globe, Info, KeyRound, UserRound } from "lucide-react";
import { toast } from "sonner";
import { ChangePasswordDialog } from "@/components/change-password-dialog";
import { Switch } from "@/components/ui/switch";
import { useProto } from "@/lib/proto-store";

export function AccountSettings() {
  const { phone, role } = useProto();
  const [reminders, setReminders] = useState(true);
  const [emergencyAlerts, setEmergencyAlerts] = useState(true);
  const [weeklySummary, setWeeklySummary] = useState(false);

  const soon = () => toast("Tính năng đang được phát triển");

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Cài đặt</h1>
        <p className="text-sm text-muted-foreground">Quản lý tài khoản và tuỳ chọn của bạn.</p>
      </header>

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">Tài khoản</h2>
        <button
          onClick={soon}
          className="mt-3 flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left"
        >
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
            <UserRound className="h-5 w-5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-semibold">{phone || "Chưa có số điện thoại"}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {role === "patient" ? "Bệnh nhân" : role === "family" ? "Người thân" : "Bác sĩ"} · Bấm
              để đổi thông tin cá nhân
            </span>
          </span>
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      </section>

      <section className="surface-card space-y-4 p-5">
        <h2 className="flex items-center gap-2 text-sm font-bold uppercase text-muted-foreground">
          <Bell className="h-4 w-4" /> Thông báo
        </h2>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium">Nhắc uống thuốc</p>
            <p className="text-xs text-muted-foreground">Nhắc theo đúng khung giờ trong phác đồ</p>
          </div>
          <Switch checked={reminders} onCheckedChange={setReminders} />
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium">Cảnh báo khẩn cấp</p>
            <p className="text-xs text-muted-foreground">
              Báo ngay khi phát hiện dấu hiệu nguy hiểm
            </p>
          </div>
          <Switch checked={emergencyAlerts} onCheckedChange={setEmergencyAlerts} />
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium">Tổng kết tuần</p>
            <p className="text-xs text-muted-foreground">Gửi báo cáo tuân thủ hằng tuần</p>
          </div>
          <Switch checked={weeklySummary} onCheckedChange={setWeeklySummary} />
        </div>
      </section>

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">Bảo mật</h2>
        <ChangePasswordDialog
          trigger={
            <button className="mt-3 flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left">
              <KeyRound className="h-5 w-5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1">
                <span className="block font-medium">Đổi mật khẩu</span>
                <span className="block text-xs text-muted-foreground">
                  Mật khẩu đăng nhập tài khoản CapyMedi
                </span>
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          }
        />
      </section>

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">Ngôn ngữ</h2>
        <button
          onClick={soon}
          className="mt-3 flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left"
        >
          <Globe className="h-5 w-5 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 font-medium">Tiếng Việt</span>
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      </section>

      <section className="surface-card flex items-center gap-3 p-5 text-sm text-muted-foreground">
        <Info className="h-4 w-4 shrink-0" />
        CapyMedi · Prototype bấm được · v0.1
      </section>
    </div>
  );
}
