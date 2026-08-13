"use client";

import { useState, type FormEvent } from "react";
import { CheckCircle2, KeyRound, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";

export function ChangePasswordDialog({
  trigger,
}: {
  trigger?: React.ReactNode;
}) {
  const { accessToken, user, updateSession } = useAuth();
  const [open, setOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  const resetState = () => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setError("");
    setSuccess(false);
    setLoading(false);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!currentPassword || !newPassword) {
      setError("Vui lòng điền đầy đủ thông tin.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Mật khẩu mới phải có ít nhất 8 ký tự.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Mật khẩu mới xác nhận không khớp.");
      return;
    }

    setError("");
    setLoading(true);

    try {
      if (!accessToken) {
        throw new Error("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
      }

      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      const data = await res.json().catch(() => null);
      if (!res.ok) {
        // 401 o day KHONG phai sai mat khau (sai mat khau hien tai la 400 -
        // xem backend/api/auth_routes.py): access_token het han/khong con
        // hop le, nen huong dan dang nhap lai thay vi bao "doi mat khau that
        // bai" chung chung.
        if (res.status === 401) {
          throw new Error("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
        }
        throw new Error(data?.detail ?? "Đổi mật khẩu thất bại.");
      }
      if (data?.access_token && user) {
        updateSession(data.access_token, { ...user, ...data.user });
      }
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(val) => {
        setOpen(val);
        if (!val) resetState();
      }}
    >
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="outline" className="gap-2">
            <KeyRound className="h-4 w-4" /> Đổi mật khẩu
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-primary" /> Đổi mật khẩu tài khoản
          </DialogTitle>
          <DialogDescription>
            Nhập mật khẩu hiện tại và mật khẩu mới để cập nhật thông tin bảo mật.
          </DialogDescription>
        </DialogHeader>

        {!success ? (
          <form onSubmit={submit} className="space-y-4 py-2">
            {error && (
              <div className="rounded-lg bg-destructive/15 p-3 text-sm font-medium text-destructive">
                {error}
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="current_pass">Mật khẩu hiện tại</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="current_pass"
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="pl-9"
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="new_pass">Mật khẩu mới</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="new_pass"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Tối thiểu 8 ký tự"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="pl-9"
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirm_new_pass">Xác nhận mật khẩu mới</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="confirm_new_pass"
                  type="password"
                  autoComplete="new-password"
                  placeholder="Nhập lại mật khẩu mới"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="pl-9"
                  required
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOpen(false)}
              >
                Hủy
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? "Đang lưu..." : "Cập nhật mật khẩu"}
              </Button>
            </div>
          </form>
        ) : (
          <div className="py-6 text-center space-y-4">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-success/15 text-success">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <p className="font-semibold text-base">Đổi mật khẩu thành công!</p>
            <p className="text-sm text-muted-foreground">
              Mật khẩu mới của bạn đã có hiệu lực lập tức.
            </p>
            <Button
              className="w-full"
              onClick={() => {
                setOpen(false);
                resetState();
              }}
            >
              Hoàn tất
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
