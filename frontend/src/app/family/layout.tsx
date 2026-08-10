"use client";

import { Bell, Images, ListChecks } from "lucide-react";
import type { ReactNode } from "react";
import { PhoneShell } from "@/components/phone-shell";

export default function FamilyLayout({ children }: { children: ReactNode }) {
  return (
    <PhoneShell
      title="Nguyễn Văn Sơn"
      subtitle="Người thân · chăm sóc bà Lan"
      tabs={[
        { to: "/family", label: "Cảnh báo", icon: <Bell className="h-5 w-5" />, exact: true },
        { to: "/family/verify", label: "Duyệt ảnh", icon: <Images className="h-5 w-5" /> },
        { to: "/family/history", label: "Lịch sử sai", icon: <ListChecks className="h-5 w-5" /> },
      ]}
    >
      {children}
    </PhoneShell>
  );
}
