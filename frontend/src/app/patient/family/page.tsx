"use client";

import Link from "next/link";
import { ChevronRight, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useProto, type AlertLevel } from "@/lib/proto-store";

const tone: Record<AlertLevel, string> = {
  low: "bg-secondary text-secondary-foreground",
  mid: "bg-warning/25 text-warning-foreground",
  high: "bg-destructive/15 text-destructive",
};

export default function PatientFamilyPage() {
  const { alerts, monitoredRelatives } = useProto();

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-extrabold">Người thân</h1>
        <p className="text-sm text-muted-foreground">
          Cảnh báo về việc uống thuốc của bạn, và theo dõi mức tuân thủ của người thân bạn quan tâm.
        </p>
      </header>

      <section>
        <h2 className="mb-2 text-sm font-bold uppercase text-muted-foreground">
          Cảnh báo liên quan
        </h2>
        {alerts.length === 0 && (
          <p className="surface-card p-6 text-center text-sm text-muted-foreground">
            Chưa có cảnh báo nào.
          </p>
        )}
        <div className="space-y-2">
          {alerts.map((a) => (
            <Link
              key={a.id}
              href={`/patient/family/alerts/${a.id}`}
              className="surface-card flex items-center gap-3 p-4"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{a.title}</p>
                <p className="truncate text-sm text-muted-foreground">{a.detail}</p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${tone[a.level]}`}
              >
                {a.at}
              </span>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-bold uppercase text-muted-foreground">
          Người thân bạn theo dõi
        </h2>
        <p className="mb-2 text-xs text-muted-foreground">
          Bạn chỉ xem được, không thay đổi được thông tin của họ.
        </p>
        {monitoredRelatives.length === 0 && (
          <p className="surface-card p-6 text-center text-sm text-muted-foreground">
            Bạn chưa theo dõi người thân nào.
          </p>
        )}
        <div className="space-y-3">
          {monitoredRelatives.map((r) => (
            <Link key={r.id} href={`/patient/family/${r.id}`} className="surface-card block p-4">
              <div className="flex items-center gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent font-bold text-accent-foreground">
                  {r.name.charAt(0)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{r.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {r.relationship} · {r.condition}
                  </p>
                </div>
                <span className="shrink-0 text-lg font-extrabold text-primary">{r.adherence}%</span>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </div>

              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${r.adherence}%` }}
                />
              </div>
              <p className="mt-1.5 text-[11px] text-muted-foreground">
                Đã uống {r.doseTakenToday}/{r.doseTotalToday} liều hôm nay
                {r.alerts.length > 0 && ` · ${r.alerts.length} cảnh báo`}
              </p>
            </Link>
          ))}
        </div>
      </section>

      <section className="surface-card p-4">
        <p className="font-semibold">Theo dõi thêm người thân</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Gửi lời mời để được người thân đồng ý cho bạn xem tình trạng uống thuốc của họ.
        </p>
        <Button
          variant="outline"
          className="mt-3 w-full"
          onClick={() => toast("Tính năng đang được phát triển")}
        >
          <UserPlus className="mr-1 h-4 w-4" /> Gửi lời mời theo dõi
        </Button>
      </section>
    </div>
  );
}
