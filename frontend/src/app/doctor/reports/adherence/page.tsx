"use client";

import { useProto } from "@/lib/proto-store";

const buckets = [
  { label: "Tuân thủ tốt (≥ 90%)", value: 35, color: "var(--success)" },
  { label: "Trung bình (70-89%)", value: 62, color: "var(--primary)" },
  { label: "Kém (50-69%)", value: 21, color: "var(--warning)" },
  { label: "Rất kém (< 50%)", value: 10, color: "var(--destructive)" },
];

export default function ReportAdherence() {
  const { patients } = useProto();
  const avg = Math.round(patients.reduce((s, p) => s + p.adherence, 0) / patients.length);
  const max = Math.max(...buckets.map((b) => b.value));
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Adherence tổng quan</h1>
        <p className="text-sm text-muted-foreground">Tuân thủ trung bình toàn hệ thống: {avg}%.</p>
      </header>
      <div className="surface-card space-y-4 p-6">
        {buckets.map((b) => (
          <div
            key={b.label}
            className="grid gap-2 sm:grid-cols-[220px_minmax(0,1fr)_60px] sm:items-center"
          >
            <p className="text-sm font-semibold">{b.label}</p>
            <div className="h-3 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full"
                style={{ width: `${(b.value / max) * 100}%`, background: b.color }}
              />
            </div>
            <p className="text-sm text-muted-foreground sm:text-right">{b.value} BN</p>
          </div>
        ))}
      </div>
    </div>
  );
}
