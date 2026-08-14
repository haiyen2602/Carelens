"use client";

import { AlertTriangle, Clock, UserRound } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { presentAlert } from "@/lib/alert-presentation";
import { useProto, type AlertLevel } from "@/lib/proto-store";

const tone: Record<AlertLevel, string> = {
  low: "bg-secondary text-secondary-foreground",
  mid: "bg-warning/25 text-warning-foreground",
  high: "bg-destructive/15 text-destructive",
};

const levelLabel: Record<AlertLevel, string> = {
  low: "Nhẹ",
  mid: "Trung bình",
  high: "Nghiêm trọng",
};

const barTone: Record<AlertLevel, string> = {
  low: "bg-primary",
  mid: "bg-warning",
  high: "bg-destructive",
};

export default function AlertsPage() {
  const { alerts, patients, setAlertStatus } = useProto();
  const visible = alerts;
  const watchedCount = patients.filter((p) => p.watch).length;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Hộp cảnh báo</h1>
        <p className="text-sm text-muted-foreground">
          Cảnh báo được tóm tắt theo vấn đề chính, bằng chứng và gợi ý xử lý để bác sĩ đọc nhanh.
        </p>
      </header>

      {visible.length === 0 && watchedCount === 0 && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Bạn chưa theo dõi bệnh nhân nào nên chưa có cảnh báo nào tới bác sĩ — bấm{" "}
          <span className="font-semibold text-foreground">Theo dõi</span> ở trang{" "}
          <Link href="/doctor/patients" className="font-semibold text-primary">
            Quản lý bệnh nhân
          </Link>{" "}
          để nhận cảnh báo của họ tại đây.
        </div>
      )}
      {visible.length === 0 && watchedCount > 0 && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Chưa có cảnh báo nào cho {watchedCount} bệnh nhân bạn đang theo dõi.
        </div>
      )}

      <div className="space-y-3">
        {visible.map((a) => {
          const alert = presentAlert(a, patients);

          return (
            <div key={a.id} className="surface-card overflow-hidden p-0">
              <div className="grid gap-0 lg:grid-cols-[8px_minmax(0,1fr)_220px]">
                <div className={barTone[a.level]} />

                <div className="min-w-0 p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full px-3 py-1 text-xs font-bold ${tone[a.level]}`}>
                      {levelLabel[a.level]}
                    </span>
                    <span className="rounded bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground">
                      {alert.statusLabel}
                    </span>
                    <span className="rounded bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground">
                      {alert.triggerLabel}
                    </span>
                  </div>

                  <h2 className="mt-3 text-lg font-bold leading-snug">{alert.title}</h2>

                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <UserRound className="h-4 w-4" />
                      {alert.patientName}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Clock className="h-4 w-4" />
                      {a.at}
                    </span>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <div className="rounded-lg bg-muted/45 p-3">
                      <p className="text-xs font-bold uppercase text-muted-foreground">
                        Vấn đề cần chú ý
                      </p>
                      <p className="mt-1 text-sm font-semibold">{alert.problem}</p>
                    </div>
                    <div className="rounded-lg bg-muted/45 p-3">
                      <p className="text-xs font-bold uppercase text-muted-foreground">
                        Bằng chứng hệ thống
                      </p>
                      <p className="mt-1 text-sm">{alert.evidence}</p>
                    </div>
                  </div>

                  <div className="mt-3 flex gap-2 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <p>
                      <span className="font-semibold">Gợi ý xử lý: </span>
                      {alert.action}
                    </p>
                  </div>
                </div>

                <div className="flex flex-col justify-between gap-3 border-t border-border p-5 lg:border-l lg:border-t-0">
                  <div className="text-sm text-muted-foreground">
                    <p className="font-semibold text-foreground">Nguồn phát hiện</p>
                    <p className="mt-1">{alert.source}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 lg:flex-col">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setAlertStatus(a.id, "acknowledged");
                        toast("Đã ghi nhận cảnh báo");
                      }}
                    >
                      Ghi nhận
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => {
                        setAlertStatus(a.id, "resolved");
                        toast.success("Đã xử lý và ghi audit log");
                      }}
                    >
                      Đánh dấu đã xử lý
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
