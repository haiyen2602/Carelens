"use client";

import { AlertTriangle, ArrowUpRight, Bell, Check, CheckCircle2, Clock3 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useProto, type AlertLevel } from "@/lib/proto-store";

const tone: Record<AlertLevel, string> = {
  low: "bg-secondary text-secondary-foreground",
  mid: "bg-warning/25 text-warning-foreground",
  high: "bg-destructive/15 text-destructive",
};

export default function FamilyAlerts() {
  const { alerts, patients, doses, setAlertStatus, escalateToDoctor } = useProto();
  const visible = alerts.filter((a) => a.target.includes("family"));

  const newCount = visible.filter((a) => a.status === "new").length;
  const processingCount = visible.filter((a) =>
    ["processing", "acknowledged"].includes(a.status),
  ).length;
  const resolvedCount = visible.filter((a) => a.status === "resolved").length;

  const patient = patients[0];
  const takenCount = doses.filter((d) => d.status === "taken").length;

  const stats = [
    { label: "Mới", value: newCount, icon: Bell, tone: "bg-destructive/12 text-destructive" },
    {
      label: "Đang xử lý",
      value: processingCount,
      icon: Clock3,
      tone: "bg-warning/25 text-warning-foreground",
    },
    {
      label: "Đã xử lý",
      value: resolvedCount,
      icon: CheckCircle2,
      tone: "bg-success/15 text-success",
    },
  ];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-extrabold">Hộp cảnh báo</h1>
        <p className="text-sm text-muted-foreground">Tổng quan tình hình bệnh nhân bạn theo dõi.</p>
      </header>

      <div className="grid grid-cols-3 gap-2">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="surface-card space-y-2 p-3 text-center">
              <span className={`mx-auto grid h-8 w-8 place-items-center rounded-full ${s.tone}`}>
                <Icon className="h-4 w-4" />
              </span>
              <p className="text-xl font-extrabold leading-none">{s.value}</p>
              <p className="text-[11px] text-muted-foreground">{s.label}</p>
            </div>
          );
        })}
      </div>

      {patient && (
        <section className="surface-card p-4">
          <div className="flex items-center gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent font-bold text-accent-foreground">
              {patient.name.charAt(0)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{patient.name}</p>
              <p className="text-xs text-muted-foreground">
                {patient.condition} · đã uống {takenCount}/{doses.length} liều hôm nay
              </p>
            </div>
            <span className="shrink-0 text-lg font-extrabold text-primary">
              {patient.adherence}%
            </span>
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${patient.adherence}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] text-muted-foreground">Tuân thủ điều trị 7 ngày qua</p>
        </section>
      )}

      <div className="space-y-3">
        {visible.length === 0 && (
          <p className="surface-card p-6 text-center text-sm text-muted-foreground">
            Chưa có cảnh báo nào. Mọi liều đang đúng giờ.
          </p>
        )}
        {visible.map((a) => (
          <section key={a.id} className="surface-card p-4">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
              <p className="min-w-0 font-bold">{a.title}</p>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${tone[a.level]}`}
              >
                {a.at}
              </span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{a.detail}</p>
            <p className="mt-2 inline-block rounded bg-muted px-2 py-1 text-[11px] font-bold uppercase text-muted-foreground">
              {a.status}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Button
                size="sm"
                onClick={() => {
                  setAlertStatus(a.id, "acknowledged");
                  toast("ACKNOWLEDGED — đang xử lý");
                }}
              >
                <Check className="mr-1 h-4 w-4" /> Đã đọc
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  escalateToDoctor(a.id);
                  toast.success("Đã chuyển thông tin tới bác sĩ");
                }}
              >
                <ArrowUpRight className="mr-1 h-4 w-4" /> Nhờ bác sĩ
              </Button>
            </div>
            {a.level === "high" && (
              <p className="mt-3 flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-xs text-destructive">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Mức nghiêm trọng: hãy liên hệ bệnh nhân ngay, cân nhắc gọi 115.
              </p>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
