"use client";

import { useProto } from "@/lib/proto-store";

export default function AdherencePage() {
  const { patients } = useProto();
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Theo dõi tuân thủ</h1>
        <p className="text-sm text-muted-foreground">
          Tỷ lệ tuân thủ 7 ngày gần nhất theo bệnh nhân.
        </p>
      </header>
      <div className="surface-card divide-y divide-border">
        {patients.map((p) => (
          <div
            key={p.id}
            className="grid items-center gap-4 p-5 sm:grid-cols-[minmax(0,1fr)_240px]"
          >
            <div className="min-w-0">
              <p className="truncate font-semibold">{p.name}</p>
              <p className="text-sm text-muted-foreground">{p.condition}</p>
            </div>
            <div>
              <p className="text-xs font-semibold text-muted-foreground">{p.adherence}%</p>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${p.adherence}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
