"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { CapyShell } from "@/components/capy/capy-shell";
import { useAuth } from "@/lib/auth";

export default function PatientLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const authChecked =
    !loading && !!user && user.role === "patient" && user.profile_completed !== false;

  useEffect(() => {
    if (loading) return;
    if (!user || user.role !== "patient") {
      router.replace("/login");
      return;
    }
    if (user.profile_completed === false) {
      router.replace("/onboarding/profile");
      return;
    }
  }, [loading, user, router]);

  if (!authChecked) {
    return (
      <div className="capymedi-theme font-sans grid min-h-screen place-items-center bg-background">
        <p className="text-sm text-muted-foreground">
          {user?.profile_completed === false ? "Đang chuyển hướng..." : "Đang kiểm tra đăng nhập..."}
        </p>
      </div>
    );
  }

  return (
    <div className="capymedi-theme font-sans">
      <CapyShell>{children}</CapyShell>
    </div>
  );
}
