"use client";

import { useProto, statusLabel } from "@/lib/proto-store";

export default function HistoryPage() {
  const { doses } = useProto();
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold">Lịch sử</h1>
      <section className="surface-card divide-y divide-border">
        {doses.map((d) => (
          <div key={d.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 p-4">
            <div className="min-w-0">
              <p className="truncate font-semibold">
                {d.time} · {d.med}
              </p>
              <p className="truncate text-sm text-muted-foreground">{d.strength}</p>
            </div>
            <span className="shrink-0 text-xs font-bold text-muted-foreground">
              {statusLabel[d.status]}
            </span>
          </div>
        ))}
      </section>
    </div>
  );
}
