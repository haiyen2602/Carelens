"use client";

import { useRouter } from "next/navigation";
import { Bell, History, Home, MessageCircle, Users } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { PhoneShell } from "@/components/phone-shell";
import { useAuth } from "@/lib/auth";

export default function PatientLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const authChecked = !loading && !!user && user.role === "patient";

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "patient") {
      router.replace("/");
    }
  }, [loading, user, router]);

  if (!authChecked) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <p className="text-sm text-muted-foreground">Đang kiểm tra đăng nhập...</p>
      </div>
    );
  }

  return (
    <PhoneShell
      title="Nguyễn Thị Lan"
      subtitle="Bệnh nhân · BN-2049"
      tabs={[
        { to: "/patient", label: "Hôm nay", icon: <Home className="h-5 w-5" />, exact: true },
        { to: "/patient/health", label: "Sức khỏe", icon: <Bell className="h-5 w-5" /> },
        { to: "/patient/assistant", label: "Trợ lý", icon: <MessageCircle className="h-5 w-5" /> },
        { to: "/patient/family", label: "Người thân", icon: <Users className="h-5 w-5" /> },
        { to: "/patient/history", label: "Lịch sử", icon: <History className="h-5 w-5" /> },
      ]}
    >
      {children}
    </PhoneShell>
  );
}
