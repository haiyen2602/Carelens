"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Cake, MapPin, Phone, Ruler, Weight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CAN_NANG_KG, CHIEU_CAO_CM, kiemTraCanNang, kiemTraChieuCao } from "@/lib/body-metrics";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import { getMyPatientProfile, updateMyPatientProfile } from "@/lib/patients";

// Onboarding bat buoc ngay sau lan dang nhap dau tien cua benh nhan
// (migration 0022, backend/api/patient_routes.py::update_my_profile). Khong
// dat o trang /register vi luong dang ky hien tai KHONG auto-login (xem
// lib/auth.tsx::register) - diem chac chan co accessToken de goi API la
// sau khi dang nhap, nen chan o day + o patient/layout.tsx (redirect neu
// !profile_completed), khong phai o trang dang ky.
export default function OnboardingProfilePage() {
  const { user, accessToken, loading, updateSession } = useAuth();
  const router = useRouter();

  const [dateOfBirth, setDateOfBirth] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [gender, setGender] = useState<string>("");
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(true);
  // Kiem tra tai cho: nguoi dung biet ngay thay vi bam Luu roi moi nhan 422.
  const chieuCao = kiemTraChieuCao(heightCm);
  const canNang = kiemTraCanNang(weightKg);

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "patient") {
      router.replace("/login");
      return;
    }
    if (!accessToken) {
      router.replace("/login");
      return;
    }

    let cancelled = false;
    void getMyPatientProfile(accessToken)
      .then((profile) => {
        if (cancelled) return;
        if (!profile) {
          setError("Không tìm thấy hồ sơ bệnh nhân.");
          return;
        }
        if (profile.profileCompleted) {
          updateSession(accessToken, { ...user, profile_completed: true });
          router.replace("/patient");
          return;
        }
        setDateOfBirth(profile.dateOfBirth ?? "");
        setPhone(profile.phone ?? "");
        setAddress(profile.address ?? "");
        setGender(profile.gender ?? "");
        setHeightCm(profile.heightCm != null ? String(profile.heightCm) : "");
        setWeightKg(profile.weightKg != null ? String(profile.weightKg) : "");
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Không tải được hồ sơ.");
      })
      .finally(() => {
        if (!cancelled) setLoadingProfile(false);
      });

    return () => {
      cancelled = true;
    };
  }, [accessToken, loading, router, updateSession, user]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!dateOfBirth || !phone.trim() || !address.trim() || !gender || !heightCm || !weightKg) {
      setError("Vui lòng nhập đầy đủ thông tin bắt buộc.");
      return;
    }
    // Chan o day nua chu khong chi dua vao min/max cua <input>: nguoi dung go
    // roi bam Enter co the bo qua validation cua trinh duyet o mot so trinh duyet.
    if (chieuCao.loi || canNang.loi) {
      setError(chieuCao.loi ?? canNang.loi ?? "");
      return;
    }

    setError("");
    setSubmitting(true);
    try {
      const profile = await updateMyPatientProfile(accessToken, {
        date_of_birth: dateOfBirth,
        phone: phone.trim(),
        address: address.trim(),
        gender,
        height_cm: Number(heightCm),
        weight_kg: Number(weightKg),
      });
      if (!profile.profileCompleted) {
        throw new Error("Hồ sơ chưa đủ thông tin bắt buộc.");
      }
      if (accessToken && user) {
        updateSession(accessToken, { ...user, profile_completed: true });
      }
      router.replace("/patient");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lưu thông tin thất bại.");
      setSubmitting(false);
    }
  };

  if (loading || loadingProfile || !user || user.role !== "patient" || user.profile_completed) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <p className="text-sm text-muted-foreground">Đang tải...</p>
      </div>
    );
  }

  return (
    <main className="grid min-h-screen place-items-center bg-background px-6 py-12">
      <div className="w-full max-w-lg space-y-6">
        <div className="flex flex-col items-center text-center">
          <Image
            src="/logo-capymedi-v2.png"
            alt="CapyMedi"
            width={56}
            height={56}
            className="h-12 w-12"
            priority
          />
          <h1 className="mt-4 text-2xl font-bold tracking-tight">Hoàn tất thông tin cá nhân</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Chào {user.full_name}, vui lòng bổ sung thông tin để CapyMedi hỗ trợ bạn tốt hơn.
          </p>
        </div>

        <form onSubmit={submit} className="surface-card space-y-4 p-6 sm:p-8">
          {error && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-sm font-medium text-destructive">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="date_of_birth">Ngày sinh</Label>
            <div className="relative">
              <Cake
                aria-hidden="true"
                className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
              />
              <Input
                id="date_of_birth"
                type="date"
                value={dateOfBirth}
                onChange={(e) => setDateOfBirth(e.target.value)}
                className="pl-9"
                max={new Date().toISOString().slice(0, 10)}
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="phone">Số điện thoại</Label>
            <div className="relative">
              <Phone
                aria-hidden="true"
                className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
              />
              <Input
                id="phone"
                type="tel"
                placeholder="09xxxxxxxx"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="pl-9"
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="address">Địa chỉ</Label>
            <div className="relative">
              <MapPin
                aria-hidden="true"
                className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
              />
              <Textarea
                id="address"
                placeholder="Số nhà, đường, phường/xã, quận/huyện, tỉnh/thành"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                className="pl-9"
                rows={2}
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="gender">Giới tính</Label>
            <Select value={gender} onValueChange={setGender}>
              <SelectTrigger id="gender">
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
              <Label htmlFor="height_cm">Chiều cao (cm)</Label>
              <div className="relative">
                <Ruler
                  aria-hidden="true"
                  className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
                />
                <Input
                  id="height_cm"
                  type="number"
                  min={CHIEU_CAO_CM.min}
                  max={CHIEU_CAO_CM.max}
                  aria-invalid={chieuCao.loi !== null || undefined}
                  placeholder="170"
                  value={heightCm}
                  onChange={(e) => setHeightCm(e.target.value)}
                  className="pl-9"
                  required
                />
              </div>
              {chieuCao.loi && <p className="text-sm text-destructive">{chieuCao.loi}</p>}
              {chieuCao.canhBao && (
                <p className="text-sm text-muted-foreground">{chieuCao.canhBao}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="weight_kg">Cân nặng (kg)</Label>
              <div className="relative">
                <Weight
                  aria-hidden="true"
                  className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"
                />
                <Input
                  id="weight_kg"
                  type="number"
                  min={CAN_NANG_KG.min}
                  max={CAN_NANG_KG.max}
                  aria-invalid={canNang.loi !== null || undefined}
                  placeholder="60"
                  value={weightKg}
                  onChange={(e) => setWeightKg(e.target.value)}
                  className="pl-9"
                  required
                />
              </div>
              {canNang.loi && <p className="text-sm text-destructive">{canNang.loi}</p>}
              {canNang.canhBao && (
                <p className="text-sm text-muted-foreground">{canNang.canhBao}</p>
              )}
            </div>
          </div>

          <Button
            type="submit"
            className="w-full h-11 text-base font-semibold"
            disabled={submitting}
          >
            {submitting ? "Đang lưu..." : "Hoàn tất"}
          </Button>
        </form>
      </div>
    </main>
  );
}
