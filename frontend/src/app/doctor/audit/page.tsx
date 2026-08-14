"use client";

import { useProto } from "@/lib/proto-store";

export default function AuditPage() {
  const { audit } = useProto();
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Audit log</h1>
        <p className="text-sm text-muted-foreground">
          {audit.length} bản ghi hội thoại AI — mỗi bản ghi là một lượt hỏi/đáp giữa bệnh nhân và
          trợ lý AI.
        </p>
      </header>
      <div className="surface-card divide-y divide-border">
        {audit.map((a) => (
          <div key={a.id} className="flex gap-4 p-4">
            <span className="w-14 shrink-0 font-mono text-sm text-muted-foreground">{a.at}</span>
            <div className="min-w-0">
              <p className="font-semibold">{a.utterance}</p>
              {a.finalResponse && (
                <p className="text-sm text-muted-foreground">{a.finalResponse}</p>
              )}
              <p className="mt-0.5 text-xs text-muted-foreground">Bệnh nhân: {a.patientId}</p>
            </div>
          </div>
        ))}
        {audit.length === 0 && (
          <p className="p-8 text-center text-sm text-muted-foreground">Chưa có bản ghi nào.</p>
        )}
      </div>
    </div>
  );
}
