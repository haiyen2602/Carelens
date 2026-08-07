"use client";

import { Bell, History, Home, MessageCircle, Users } from "lucide-react";
import type { ReactNode } from "react";
import { PhoneShell } from "@/components/phone-shell";

export default function PatientLayout({ children }: { children: ReactNode }) {
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
