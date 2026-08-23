"use client";

import { useState, type FormEvent } from "react";
import { Cake, CheckCircle2, MapPin, Phone, Ruler, UserRound, Weight } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CAN_NANG_KG, CHIEU_CAO_CM, kiemTraCanNang, kiemTraChieuCao } from "@/lib/body-metrics";
import { getMyPatientProfile, updateMyPatientProfile } from "@/lib/patients";
import { useAuth } from "@/lib/auth";

// Doi thong tin ca nhan SAU khi da hoan tat onboarding (khac
// onboarding/profile/page.tsx - bat buoc dien lan dau, tat ca field required).
// O day tat ca field la TUY CHON: benh nhan co the chi sua dung 1 truong (vd
// so dien thoai) ma khong bi ep dien lai nhung truong con lai chua co san.
// Dung chung 1 endpoint PATCH /api/patients/me voi onboarding (xem
// lib/patients.ts::updateMyPatientProfile) - KHONG co field ho ten: chua co
// API cho benh nhan tu doi ten minh (chi admin doi duoc qua AccountUpdateRequest).
export function EditPersonalInfoDialog({ trigger }: { trigger?: React.ReactNode }) {
  const { accessToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [gender, setGender] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  const chieuCao = kiemTraChieuCao(heightCm);
  const canNang = kiemTraCanNang(weightKg);

  const resetState = () => {
    setDateOfBirth("");
    setPhone("");
    setAddress("");
    setGender("");
    setHeightCm("");
    setWeightKg("");
    setError("");
    setSuccess(false);
    setLoading(false);
    setLoadingProfile(false);
  };

  const napHoSo = async () => {
    setLoadingProfile(true);
    try {
      const hoSo = await getMyPatientProfile(accessToken);
      if (hoSo) {
        setDateOfBirth(hoSo.dateOfBirth ?? "");
        setPhone(hoSo.phone ?? "");
        setAddress(hoSo.address ?? "");
        setGender(hoSo.gender ?? "");
        setHeightCm(hoSo.heightCm != null ? String(hoSo.heightCm) : "");
        setWeightKg(hoSo.weightKg != null ? String(hoSo.weightKg) : "");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được thông tin hiện có.");
    } finally {
      setLoadingProfile(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (chieuCao.loi || canNang.loi) {
      setError(chieuCao.loi ?? canNang.loi ?? "");
      return;
    }

    setError("");
    setLoading(true);
    try {
      await updateMyPatientProfile(accessToken, {
        date_of_birth: dateOfBirth || undefined,
        phone: phone.trim() || undefined,
        address: address.trim() || undefined,
        gender: gender || undefined,
        height_cm: heightCm ? Number(heightCm) : undefined,
        weight_kg: weightKg ? Number(weightKg) : undefined,
      });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lưu thông tin thất bại.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(val) => {
        setOpen(val);
        if (val) {
          resetState();
          void napHoSo();
        }
      }}
    >
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="outline" className="gap-2">
            <UserRound className="h-4 w-4" /> Đổi thông tin cá nhân
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserRound className="h-5 w-5 text-primary" /> Thông tin cá nhân
          </DialogTitle>
          <DialogDescription>
            Cập nhật số điện thoại, ngày sinh, địa chỉ và các chỉ số cơ thể của bạn. Chỉ sửa trường
            nào cần đổi — để trống thì giữ nguyên giá trị cũ.
          </DialogDescription>
        </DialogHeader>

        {!success ? (
          <form onSubmit={submit} className="space-y-4 py-2">
            {error && (
              <div className="rounded-lg bg-destructive/15 p-3 text-sm font-medium text-destructive">
                {error}
              </div>
            )}
            {loadingProfile && (
              <p className="text-sm text-muted-foreground">Đang tải thông tin hiện có...</p>
            )}

            <div className="space-y-2">
              <Label htmlFor="edit_date_of_birth">Ngày sinh</Label>
              <div className="relative">
                <Cake className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="edit_date_of_birth"
                  type="date"
                  value={dateOfBirth}
                  onChange={(e) => setDateOfBirth(e.target.value)}
                  className="pl-9"
                  max={new Date().toISOString().slice(0, 10)}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit_phone">Số điện thoại</Label>
              <div className="relative">
                <Phone className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="edit_phone"
                  type="tel"
                  placeholder="09xxxxxxxx"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit_address">Địa chỉ</Label>
              <div className="relative">
                <MapPin className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Textarea
                  id="edit_address"
                  placeholder="Số nhà, đường, phường/xã, quận/huyện, tỉnh/thành"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  className="pl-9"
                  rows={2}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit_gender">Giới tính</Label>
              <Select value={gender} onValueChange={setGender}>
                <SelectTrigger id="edit_gender">
                  <SelectValue placeholder="Chọn giới tính" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="nam">Nam</SelectItem>
                  <SelectItem value="nu">Nữ</SelectItem>
                  <SelectItem value="khac">Khác</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="edit_height_cm">Chiều cao (cm)</Label>
                <div className="relative">
                  <Ruler className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="edit_height_cm"
                    type="number"
                    min={CHIEU_CAO_CM.min}
                    max={CHIEU_CAO_CM.max}
                    aria-invalid={chieuCao.loi !== null || undefined}
                    placeholder="170"
                    value={heightCm}
                    onChange={(e) => setHeightCm(e.target.value)}
                    className="pl-9"
                  />
                </div>
                {chieuCao.loi && <p className="text-sm text-destructive">{chieuCao.loi}</p>}
                {chieuCao.canhBao && (
                  <p className="text-sm text-muted-foreground">{chieuCao.canhBao}</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit_weight_kg">Cân nặng (kg)</Label>
                <div className="relative">
                  <Weight className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="edit_weight_kg"
                    type="number"
                    min={CAN_NANG_KG.min}
                    max={CAN_NANG_KG.max}
                    aria-invalid={canNang.loi !== null || undefined}
                    placeholder="60"
                    value={weightKg}
                    onChange={(e) => setWeightKg(e.target.value)}
                    className="pl-9"
                  />
                </div>
                {canNang.loi && <p className="text-sm text-destructive">{canNang.loi}</p>}
                {canNang.canhBao && (
                  <p className="text-sm text-muted-foreground">{canNang.canhBao}</p>
                )}
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                Hủy
              </Button>
              <Button type="submit" disabled={loading || loadingProfile}>
                {loading ? "Đang lưu..." : "Lưu thay đổi"}
              </Button>
            </div>
          </form>
        ) : (
          <div className="py-6 text-center space-y-4">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-success/15 text-success">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <p className="font-semibold text-base">Đã lưu thông tin!</p>
            <p className="text-sm text-muted-foreground">
              Thông tin cá nhân của bạn đã được cập nhật.
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
