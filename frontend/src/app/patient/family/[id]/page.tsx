"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useProto, type DoseHistoryStatus } from "@/lib/proto-store";

const historyTone: Record<DoseHistoryStatus, string> = {
  taken: "bg-success text-success-foreground",
  late: "bg-warning text-warning-foreground",
  missed: "bg-destructive text-destructive-foreground",
};

const historyLabel: Record<DoseHistoryStatus, string> = {
  taken: "Đúng giờ",
  late: "Uống trễ",
  missed: "Bỏ liều",
};

export default function MonitoredRelativeDetailPage() {
  const params = useParams<{ id: string }>();
  const { monitoredRelatives } = useProto();
  const relative = monitoredRelatives.find((r) => r.id === params.id);

  if (!relative) {
    return (
      <div className="space-y-4">
        <Link href="/patient/family" className="flex items-center gap-1.5 text-sm text-primary">
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </Link>
        <p className="surface-card p-6 text-center text-sm text-muted-foreground">
          Không tìm thấy người thân này.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Link href="/patient/family" className="flex items-center gap-1.5 text-sm text-primary">
        <ArrowLeft className="h-4 w-4" /> Quay lại
      </Link>

      <section className="surface-card p-5">
        <div className="flex items-center gap-3">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent text-lg font-bold text-accent-foreground">
            {relative.name.charAt(0)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-bold">{relative.name}</p>
            <p className="truncate text-sm text-muted-foreground">
              {relative.relationship} · {relative.age} tuổi · {relative.condition}
            </p>
          </div>
          <span className="shrink-0 text-xl font-extrabold text-primary">
            {relative.adherence}%
          </span>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary"
            style={{ width: `${relative.adherence}%` }}
          />
        </div>
        <p className="mt-1.5 text-[11px] text-muted-foreground">Tuân thủ điều trị 7 ngày qua</p>
      </section>

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">Đơn thuốc hiện tại</h2>
        <div className="mt-3 divide-y divide-border">
          {relative.prescriptions.map((p) => (
            <div key={p.id} className="py-3">
              <p className="font-semibold">{p.med}</p>
              <p className="text-sm text-muted-foreground">
                {p.dose} · {p.schedule}
              </p>
            </div>
          ))}
          {relative.prescriptions.length === 0 && (
            <p className="py-3 text-sm text-muted-foreground">Chưa có đơn thuốc nào.</p>
          )}
        </div>
      </section>

      <section className="surface-card p-5">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">
          Lịch sử tuân thủ 7 ngày qua
        </h2>
        <div className="mt-3 grid grid-cols-7 gap-1.5">
          {relative.weekHistory.map((h) => (
            <div key={h.day} className="text-center">
              <div
                className={`mx-auto grid h-8 w-8 place-items-center rounded-lg text-[10px] font-bold ${historyTone[h.status]}`}
              >
                {h.day}
              </div>
            </div>
          ))}
        </div>
        <ul className="mt-4 space-y-1.5 text-xs text-muted-foreground">
          {(["taken", "late", "missed"] as DoseHistoryStatus[]).map((s) => (
            <li key={s} className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${historyTone[s]}`} />
              {historyLabel[s]}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
