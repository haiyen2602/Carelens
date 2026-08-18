"use client";

import { useRouter } from "next/navigation";
import { Heart, History, Home, MessageCircle, Users } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { PhoneShell } from "@/components/phone-shell";
import { useAuth } from "@/lib/auth";

export default function PatientLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const authChecked =
    !loading && !!user && user.role === "patient" && user.profile_completed !== false;

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "patient") {
      router.replace("/");
      return;
    }
    // Chan tat ca duong vao /patient/* neu chua hoan tat onboarding
    // (migration 0022) - khong chi chan luc dang nhap (page.tsx), vi user
    // co the deep-link/back thang vao /patient/xxx.
    if (user.profile_completed === false) {
      router.replace("/onboarding/profile");
    }
  }, [loading, user, router]);

  if (!authChecked) {
    return (
      <div className="capymedi-theme font-sans grid min-h-screen place-items-center bg-background">
        <p className="text-sm text-muted-foreground">Đang kiểm tra đăng nhập...</p>
      </div>
    );
  }

  return (
    <div className="capymedi-theme font-sans">
      <PhoneShell
        title={user?.full_name ?? ""}
        subtitle={`Bệnh nhân · ${user?.patient_id ?? ""}`}
        tabs={[
          { to: "/patient", label: "Hôm nay", icon: <Home className="h-5 w-5" />, exact: true },
          { to: "/patient/health", label: "Sức khỏe", icon: <Heart className="h-5 w-5" /> },
          { to: "/patient/assistant", label: "Capy AI", icon: <MessageCircle className="h-5 w-5" /> },
          { to: "/patient/family", label: "Người thân", icon: <Users className="h-5 w-5" /> },
          { to: "/patient/history", label: "Lịch sử", icon: <History className="h-5 w-5" /> },
        ]}
      >
        {children}
      </PhoneShell>
    </div>
  );
}
