"use client";

import { Eye, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useProto } from "@/lib/proto-store";

export default function PatientsPage() {
  const { patients, toggleWatch, doses } = useProto();
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const list = patients.filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="space-y-6">
      <header className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-extrabold tracking-tight">Danh sách bệnh nhân</h1>
          <p className="text-sm text-muted-foreground">
            Filter theo tên, mở hồ sơ để xem chi tiết.
          </p>
        </div>
        <Input
          placeholder="Tìm bệnh nhân…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full sm:w-64"
        />
      </header>

      <div className="space-y-3">
        {list.map((p) => (
          <div key={p.id} className="surface-card p-5">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent font-bold text-accent-foreground">
                  {p.name.charAt(0)}
                </span>
                <div className="min-w-0">
                  <p className="flex items-center gap-2 truncate font-semibold">
                    {p.name}
                    {p.watch && (
                      <span className="inline-flex shrink-0 items-center gap-1 rounded bg-warning/25 px-1.5 py-0.5 text-[11px] font-semibold text-warning-foreground">
                        <ShieldAlert className="h-3 w-3" /> Theo dõi
                      </span>
                    )}
                  </p>
                  <p className="truncate text-sm text-muted-foreground">
                    {p.age} tuổi · {p.condition}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-4">
                <div className="hidden w-36 sm:block">
                  <p className="text-xs text-muted-foreground">Tuân thủ {p.adherence}%</p>
                  <Progress value={p.adherence} className="mt-1 h-2" />
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setOpenId(openId === p.id ? null : p.id)}
                >
                  <Eye className="mr-1 h-4 w-4" /> Hồ sơ
                </Button>
                <Button variant="ghost" size="sm" onClick={() => toggleWatch(p.id)}>
                  {p.watch ? "Bỏ theo dõi" : "Theo dõi"}
                </Button>
              </div>
            </div>

            {openId === p.id && (
              <div className="mt-5 space-y-3 rounded-lg bg-muted p-4">
                <p className="text-sm font-semibold">Lịch sử liều hôm nay</p>
                <ul className="space-y-2 text-sm">
                  {doses.map((d) => (
                    <li key={d.id} className="flex items-center justify-between gap-3">
                      <span className="min-w-0 truncate">
                        {d.time} · {d.med} {d.strength}
                      </span>
                      <span className="shrink-0 text-xs font-semibold text-muted-foreground">
                        {d.status.toUpperCase()}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
