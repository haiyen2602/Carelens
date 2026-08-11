"use client";

import { Lock, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { SYSTEM_AUDIT, type AccountRole, roleLabel } from "@/lib/admin-mock";

const roleTone: Record<string, string> = {
  doctor: "bg-success/15 text-success",
  patient: "bg-primary/10 text-primary",
  caregiver: "bg-warning/25 text-warning-foreground",
  admin: "bg-accent text-accent-foreground",
  "Hệ thống": "bg-muted text-muted-foreground",
};

export default function AdminAuditPage() {
  const [q, setQ] = useState("");
  const [role, setRole] = useState<"all" | AccountRole | "Hệ thống">("all");

  const list = useMemo(
    () =>
      SYSTEM_AUDIT.filter((a) => {
        const matchQ =
          a.actor.toLowerCase().includes(q.toLowerCase()) ||
          a.action.toLowerCase().includes(q.toLowerCase());
        const matchRole = role === "all" || a.role === role;
        return matchQ && matchRole;
      }),
    [q, role],
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Log hệ thống</h1>
        <p className="text-sm text-muted-foreground">
          {SYSTEM_AUDIT.length} bản ghi audit — bao gồm hành động của bác sĩ, agent và quản trị
          viên. Không ai được phép sửa/xoá bản ghi audit log.
        </p>
      </header>

      <div className="flex items-start gap-3 rounded-xl border border-warning/40 bg-warning/10 p-4">
        <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warning-foreground" />
        <p className="text-sm text-warning-foreground">
          Audit log chỉ đọc (read-only), kể cả với quản trị viên — đây là ràng buộc an toàn của sản
          phẩm.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm theo người thực hiện, hành động..."
            className="pl-9"
          />
        </div>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as "all" | AccountRole | "Hệ thống")}
          className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
        >
          <option value="all">Vai trò: Tất cả</option>
          <option value="admin">Quản trị</option>
          <option value="doctor">Bác sĩ</option>
          <option value="patient">Bệnh nhân</option>
          <option value="caregiver">Người thân</option>
          <option value="Hệ thống">Hệ thống / Agent</option>
        </select>
      </div>

      <div className="surface-card divide-y divide-border">
        {list.map((a) => (
          <div key={a.id} className="flex flex-wrap items-start gap-4 p-4">
            <div className="w-24 shrink-0">
              <p className="text-sm font-semibold">{a.date}</p>
              <p className="font-mono text-xs text-muted-foreground">{a.at}</p>
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{a.actor}</p>
              <p className="text-sm text-muted-foreground">{a.action}</p>
              {a.target && (
                <p className="mt-1 text-xs text-muted-foreground">Đối tượng: {a.target}</p>
              )}
            </div>
            <span
              className={`shrink-0 rounded-md px-2 py-1 text-xs font-semibold ${roleTone[a.role] ?? "bg-muted text-muted-foreground"}`}
            >
              {a.role === "Hệ thống" ? "Hệ thống" : roleLabel[a.role as AccountRole]}
            </span>
          </div>
        ))}
        {list.length === 0 && (
          <p className="p-8 text-center text-muted-foreground">Không tìm thấy bản ghi phù hợp.</p>
        )}
      </div>
    </div>
  );
}
