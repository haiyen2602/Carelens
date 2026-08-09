"use client";

import { toast } from "sonner";
import { Button } from "@/components/ui/button";
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

export default function AlertsPage() {
  const { alerts, setAlertStatus } = useProto();
  const visible = alerts.filter((a) => a.target.includes("doctor"));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Hộp cảnh báo</h1>
        <p className="text-sm text-muted-foreground">
          Cảnh báo được đẩy tới bác sĩ khi vượt ngưỡng hoặc người thân chuyển lên.
        </p>
      </header>

      {visible.length === 0 && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Chưa có cảnh báo nào tới bác sĩ.
        </div>
      )}

      <div className="space-y-3">
        {visible.map((a) => (
          <div key={a.id} className="surface-card p-5">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4">
              <div className="min-w-0">
                <p className="truncate text-lg font-bold">{a.title}</p>
                <p className="mt-1 text-sm text-muted-foreground">{a.detail}</p>
              </div>
              <div className="shrink-0 text-right">
                <span className={`rounded-full px-3 py-1 text-xs font-bold ${tone[a.level]}`}>
                  {levelLabel[a.level]}
                </span>
                <p className="mt-2 text-xs text-muted-foreground">{a.at}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="rounded bg-muted px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">
                {a.status}
              </span>
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
        ))}
      </div>
    </div>
  );
}
