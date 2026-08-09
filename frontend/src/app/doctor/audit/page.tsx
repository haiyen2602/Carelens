"use client";

import { useProto } from "@/lib/proto-store";

export default function AuditPage() {
  const { audit } = useProto();
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Audit log</h1>
        <p className="text-sm text-muted-foreground">
          {audit.length} bản ghi — cập nhật realtime khi bạn thao tác trong prototype.
        </p>
      </header>
      <div className="surface-card divide-y divide-border">
        {audit.map((a) => (
          <div key={a.id} className="flex gap-4 p-4">
            <span className="w-14 shrink-0 font-mono text-sm text-muted-foreground">{a.at}</span>
            <div className="min-w-0">
              <p className="font-semibold">{a.actor}</p>
              <p className="text-sm text-muted-foreground">{a.action}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
