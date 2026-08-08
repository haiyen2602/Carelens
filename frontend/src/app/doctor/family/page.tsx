"use client";

import { Phone } from "lucide-react";
import { useProto } from "@/lib/proto-store";

const relations = ["Con trai", "Con gái", "Cháu"];

export default function FamilyListPage() {
  const { patients } = useProto();
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Family member list</h1>
        <p className="text-sm text-muted-foreground">
          Người thân nhận cảnh báo và xác minh ảnh uống thuốc.
        </p>
      </header>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {patients.map((p, i) => (
          <div key={p.id} className="surface-card p-5">
            <p className="font-semibold">
              {relations[i % relations.length]} của {p.name}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">Bệnh nhân: {p.name}</p>
            <p className="mt-3 flex items-center gap-2 text-sm text-primary">
              <Phone className="h-4 w-4" /> 09xx xxx {String(100 + i)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
