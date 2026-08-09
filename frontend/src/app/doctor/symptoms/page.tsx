"use client";

import { useProto } from "@/lib/proto-store";

const seed = [
  { id: "s1", at: "06:45", text: "Khó thở, đau ngực nhẹ khi đi bộ", level: "high" as const },
  { id: "s2", at: "21:10", text: "Chóng mặt sau khi uống thuốc huyết áp", level: "mid" as const },
];

const tone = {
  low: "bg-secondary text-secondary-foreground",
  mid: "bg-warning/25 text-warning-foreground",
  high: "bg-destructive/12 text-destructive",
};

export default function SymptomsPage() {
  const { healthLog } = useProto();
  const items = [...healthLog, ...seed];
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Nhật ký triệu chứng</h1>
        <p className="text-sm text-muted-foreground">
          {items.length} bản ghi từ bệnh nhân và AI triage.
        </p>
      </header>
      <div className="surface-card divide-y divide-border">
        {items.map((s) => (
          <div key={s.id} className="flex items-start gap-4 p-5">
            <span className="w-14 shrink-0 font-mono text-sm text-muted-foreground">{s.at}</span>
            <p className="min-w-0 flex-1">{s.text}</p>
            <span
              className={`shrink-0 rounded-md px-2 py-1 text-xs font-semibold ${tone[s.level]}`}
            >
              {s.level === "high" ? "Nghiêm trọng" : s.level === "mid" ? "Trung bình" : "Nhẹ"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
