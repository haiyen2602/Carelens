"use client";

import { Phone, Users } from "lucide-react";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { useProto } from "@/lib/proto-store";

export default function FamilyListPage() {
  const { patients, familyContacts } = useProto();
  const [q, setQ] = useState("");

  const withDisplayId = patients.map((p, i) => ({
    ...p,
    displayId: `BN${String(i + 1).padStart(4, "0")}`,
  }));
  const query = q.trim().toLowerCase();
  const list = withDisplayId.filter(
    (p) => p.name.toLowerCase().includes(query) || p.displayId.toLowerCase().includes(query),
  );

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Family member list</h1>
          <p className="text-sm text-muted-foreground">
            Người thân nhận cảnh báo và xác minh ảnh uống thuốc.
          </p>
        </div>
        <Input
          placeholder="Tìm theo tên hoặc ID bệnh nhân…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full sm:w-64"
        />
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {list.map((p) => {
          const contacts = familyContacts.filter((c) => c.patientId === p.id);
          return (
            <div key={p.id} className="surface-card p-5">
              <p className="font-semibold">{p.name}</p>
              <p className="mt-0.5 text-sm text-muted-foreground">
                ID: {p.displayId} · {p.age} tuổi
              </p>

              <div className="mt-3 space-y-2.5 border-t border-border pt-3">
                {contacts.length === 0 && (
                  <p className="text-sm text-muted-foreground">Chưa có người thân được thêm.</p>
                )}
                {contacts.map((c) => (
                  <div key={c.id} className="flex items-center justify-between gap-2">
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 truncate text-sm font-medium">
                        <Users className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        {c.name}
                      </span>
                      <span className="ml-5 text-xs text-muted-foreground">{c.relation}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5 text-sm text-primary">
                      <Phone className="h-3.5 w-3.5 shrink-0" /> {c.phone}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {list.length === 0 && (
          <p className="col-span-full py-10 text-center text-sm text-muted-foreground">
            Không tìm thấy bệnh nhân phù hợp.
          </p>
        )}
      </div>
    </div>
  );
}
