"use client";

import { AlertTriangle, ChevronRight, Clock, UserRound, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  const [openId, setOpenId] = useState<string | null>(null);
  const watchedCount = patients.filter((p) => p.watch).length;

  const selected = alerts.find((a) => a.id === openId) ?? null;
  const selectedView = selected ? presentAlert(selected, patients) : null;
  const selectedPatient = selected ? patients.find((p) => p.id === selected.patientId) : undefined;

  const doAction = (id: string, status: "acknowledged" | "resolved" | "dismissed", msg: string) => {
    setAlertStatus(id, status);
    if (status === "resolved") toast.success(msg);
    else toast(msg);
    setOpenId(null);
  };

  return (
    <div className="space-y-6">
      {alerts.length === 0 && watchedCount === 0 && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Bạn chưa theo dõi bệnh nhân nào nên chưa có cảnh báo nào tới bác sĩ — bấm{" "}
          <span className="font-semibold text-foreground">Theo dõi</span> ở trang{" "}
          <Link href="/doctor/patients" className="font-semibold text-primary">
            Quản lý bệnh nhân
          </Link>{" "}
          để nhận cảnh báo của họ tại đây.
        </div>
      )}
      {alerts.length === 0 && watchedCount > 0 && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Chưa có cảnh báo nào cho {watchedCount} bệnh nhân bạn đang theo dõi.
        </div>
      )}

      <div className="space-y-2">
        {alerts.map((a) => {
          const alert = presentAlert(a, patients);
          const handled = a.status === "resolved" || a.status === "dismissed";

          return (
            <button
              key={a.id}
              onClick={() => setOpenId(a.id)}
              className={`surface-card flex w-full items-center gap-0 overflow-hidden p-0 text-left transition-colors hover:bg-muted/40 ${
                handled ? "opacity-60" : ""
              }`}
            >
              <span className={`w-1.5 shrink-0 self-stretch ${barTone[a.level]}`} />

              <span className="flex min-w-0 flex-1 items-center gap-3 p-4">
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${tone[a.level]}`}
                    >
                      {levelLabel[a.level]}
                    </span>
                    <span className="truncate font-bold">{alert.title}</span>
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <UserRound className="h-3.5 w-3.5" />
                      {alert.patientName}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5" />
                      {a.at}
                    </span>
                    <span className="font-medium">{alert.statusLabel}</span>
                  </span>
                </span>

                <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" />
              </span>
            </button>
          );
        })}
      </div>

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setOpenId(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          {selected && selectedView && (
            <>
              <DialogHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-bold ${tone[selected.level]}`}
                  >
                    {levelLabel[selected.level]}
                  </span>
                  <span className="rounded bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground">
                    {selectedView.statusLabel}
                  </span>
                  <span className="rounded bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground">
                    {selectedView.triggerLabel}
                  </span>
                </div>
                <DialogTitle className="pt-2 text-left text-lg">{selectedView.title}</DialogTitle>
              </DialogHeader>

              <div className="space-y-4">
                <div className="rounded-lg border border-border p-3 text-sm">
                  <p className="font-semibold">{selectedView.patientName}</p>
                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
                    {selectedPatient && (
                      <>
                        <span>{selectedPatient.age} tuổi</span>
                        <span>{selectedPatient.condition}</span>
                        <span>Tuân thủ {selectedPatient.adherence}%</span>
                      </>
                    )}
                    <span className="inline-flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5" />
                      {selected.at}
                    </span>
                  </div>
                </div>

                <div className="rounded-lg bg-muted/45 p-3">
                  <p className="text-xs font-bold uppercase text-muted-foreground">
                    Vấn đề cần chú ý
                  </p>
                  <p className="mt-1 text-sm font-semibold">{selectedView.problem}</p>
                </div>

                <div className="rounded-lg bg-muted/45 p-3">
                  <p className="text-xs font-bold uppercase text-muted-foreground">
                    Bằng chứng hệ thống
                  </p>
                  <p className="mt-1 text-sm">{selectedView.evidence}</p>
                  <p className="mt-2 text-xs text-muted-foreground">{selectedView.source}</p>
                </div>

                <div className="flex gap-2 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <p>
                    <span className="font-semibold">Gợi ý xử lý: </span>
                    {selectedView.action}
                  </p>
                </div>

                <div className="grid gap-2 sm:grid-cols-2">
                  <Button variant="outline" size="sm" asChild>
                    <Link href="/doctor/patients">
                      <UserRound className="mr-1 h-4 w-4" /> Hồ sơ bệnh nhân
                    </Link>
                  </Button>
                  <Button variant="outline" size="sm" asChild>
                    <Link href="/doctor/family">
                      <Users className="mr-1 h-4 w-4" /> Liên hệ người thân
                    </Link>
                  </Button>
                </div>
              </div>

              <DialogFooter className="gap-2 sm:justify-between">
                <Button
                  variant="ghost"
                  className="text-destructive"
                  onClick={() => doAction(selected.id, "dismissed", "Đã từ chối cảnh báo")}
                >
                  Từ chối
                </Button>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => doAction(selected.id, "acknowledged", "Đã ghi nhận cảnh báo")}
                  >
                    Ghi nhận
                  </Button>
                  <Button
                    onClick={() => doAction(selected.id, "resolved", "Đã xử lý và ghi audit log")}
                  >
                    Đánh dấu đã xử lý
                  </Button>
                </div>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
