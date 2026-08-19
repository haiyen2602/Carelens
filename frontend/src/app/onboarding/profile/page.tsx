"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Cake, MapPin, Phone, Ruler, Weight } from "lucide-react";
import { Button } from "@/components/ui/button";
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
import { useAuth } from "@/lib/auth";

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

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "patient") {
      router.replace("/");
      return;
    }
    if (user.profile_completed) {
      router.replace("/patient");
    }
  }, [loading, user, router]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!dateOfBirth || !phone.trim() || !address.trim() || !gender) {
      setError("Vui lòng nhập đầy đủ thông tin bắt buộc.");
      return;
    }

    setError("");
    setSubmitting(true);
    try {
      const res = await fetch("/api/patients/me", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({
          date_of_birth: dateOfBirth,
          phone: phone.trim(),
          address: address.trim(),
          gender,
          height_cm: heightCm ? Number(heightCm) : undefined,
          weight_kg: weightKg ? Number(weightKg) : undefined,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.detail ?? "Lưu thông tin thất bại.");
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

  if (loading || !user || user.role !== "patient" || user.profile_completed) {
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
              <Cake aria-hidden="true" className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
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
              <Phone aria-hidden="true" className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
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
              <MapPin aria-hidden="true" className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
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
                <Ruler aria-hidden="true" className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="height_cm"
                  type="number"
                  min={0}
                  max={300}
                  placeholder="170"
                  value={heightCm}
                  onChange={(e) => setHeightCm(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="weight_kg">Cân nặng (kg)</Label>
              <div className="relative">
                <Weight aria-hidden="true" className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="weight_kg"
                  type="number"
                  min={0}
                  max={500}
                  placeholder="60"
                  value={weightKg}
                  onChange={(e) => setWeightKg(e.target.value)}
                  className="pl-9"
                />
              </div>
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
