"use client";

import { useState } from "react";
import { Bell, ChevronRight, Globe, Info, KeyRound, UserRound } from "lucide-react";
import { toast } from "sonner";
import { ChangePasswordDialog } from "@/components/change-password-dialog";
import { EditPersonalInfoDialog } from "@/components/edit-personal-info-dialog";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

export function AccountSettings() {
  const { phone, role } = useProto();
  const { user } = useAuth();
  const [reminders, setReminders] = useState(true);
  const [emergencyAlerts, setEmergencyAlerts] = useState(true);
  const [weeklySummary, setWeeklySummary] = useState(false);

  // THEM 2026-08-17: tai khoan tao qua Login with Google chua co mat khau -
  // nhan phai la "Đặt mật khẩu", biet TRUOC khi mo dialog (neu vao trong roi
  // moi biet thi nguoi dung da nhap xong 3 o mat khau).
  //
  // GHI CHU 2026-08-17: nhan nay phu thuoc DU LIEU cua tung tai khoan
  // (`auth_provider`), khong phai moi truong - cung 1 email co the thay
  // "Đặt mật khẩu" o may nay va "Đổi mật khẩu" o may khac neu 2 DB co 2 trang
  // thai khac nhau (tai khoan sinh ra tu Google vs tai khoan cu moi lien ket
  // Google sau). Copy ben duoi noi ro dieu do de khong bi hieu la loi hien thi.
  const chuaCoMatKhau = user?.auth_provider === "google";

  const soon = () => toast("Tính năng đang được phát triển");

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Cài đặt</h1>
        <p className="text-sm text-muted-foreground">Quản lý tài khoản và tuỳ chọn của bạn.</p>
      </header>

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">Tài khoản</h2>
        {/* SUA 2026-08-23: hang nay tung chi hien toast "dang phat trien".
            Chi wire EditPersonalInfoDialog cho role=patient - backend
            (GET/PATCH /api/v1/patients/me) chi phuc vu tai khoan co
            patient_id gan voi minh (thuc te chi role=patient), family/doctor
            goi se 403 nen van giu nut toast cu cho ho. */}
        {role === "patient" ? (
          <EditPersonalInfoDialog
            trigger={
              <button className="mt-3 flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
                  <UserRound className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">
                    {phone || "Chưa có số điện thoại"}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    Bệnh nhân · Bấm để đổi thông tin cá nhân
                  </span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </button>
            }
          />
        ) : (
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
                {role === "family" ? "Người thân" : "Bác sĩ"} · Bấm để đổi thông tin cá nhân
              </span>
            </span>
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>
        )}
      </section>

      <section className="surface-card space-y-4 p-5">
        <h2 className="flex items-center gap-2 text-sm font-bold uppercase text-muted-foreground">
          <Bell className="h-4 w-4" /> Thông báo
        </h2>
        <p className="rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
          Các tuỳ chọn dưới đây hiện chỉ đổi trên màn hình này, chưa được lưu vào hệ thống.
        </p>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium">Nhắc uống thuốc</p>
            <p className="text-xs text-muted-foreground">Nhắc theo đúng khung giờ trong phác đồ</p>
          </div>
          <Switch aria-label="Nhắc uống thuốc" checked={reminders} onCheckedChange={setReminders} />
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium">Cảnh báo khẩn cấp</p>
            <p className="text-xs text-muted-foreground">
              Báo ngay khi phát hiện dấu hiệu nguy hiểm
            </p>
          </div>
          <Switch
            aria-label="Cảnh báo khẩn cấp"
            checked={emergencyAlerts}
            onCheckedChange={setEmergencyAlerts}
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium">Tổng kết tuần</p>
            <p className="text-xs text-muted-foreground">Gửi báo cáo tuân thủ hằng tuần</p>
          </div>
          <Switch
            aria-label="Tổng kết tuần"
            checked={weeklySummary}
            onCheckedChange={setWeeklySummary}
          />
        </div>
      </section>

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">Bảo mật</h2>
        <ChangePasswordDialog
          trigger={
            <button className="mt-3 flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left">
              <KeyRound className="h-5 w-5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1">
                <span className="block font-medium">
                  {chuaCoMatKhau ? "Đặt mật khẩu" : "Đổi mật khẩu"}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {chuaCoMatKhau
                    ? "Tài khoản tạo qua Google chưa có mật khẩu — đặt mật khẩu để đăng nhập được cả hai cách"
                    : "Tài khoản này đã có mật khẩu riêng — đổi sang mật khẩu mới"}
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
