"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Camera, Check, Clock, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useProto, statusLabel, type AlertLevel } from "@/lib/proto-store";

const tone: Record<AlertLevel, string> = {
  low: "bg-secondary text-secondary-foreground",
  mid: "bg-warning/25 text-warning-foreground",
  high: "bg-destructive/15 text-destructive",
};

export default function PatientAlertDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { alerts, doses, respondDose, sendPhoto, remindAgain } = useProto();
  const alert = alerts.find((a) => a.id === params.id);
  const dose = alert?.doseId ? doses.find((d) => d.id === alert.doseId) : undefined;

  if (!alert) {
    return (
      <div className="space-y-4">
        <Link href="/patient/family" className="flex items-center gap-1.5 text-sm text-primary">
          <ArrowLeft className="h-4 w-4" /> Quay lại
        </Link>
        <p className="surface-card p-6 text-center text-sm text-muted-foreground">
          Không tìm thấy cảnh báo này.
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
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
          <h1 className="min-w-0 text-lg font-extrabold">{alert.title}</h1>
          <span
            className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${tone[alert.level]}`}
          >
            {alert.at}
          </span>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">{alert.detail}</p>
        <p className="mt-3 inline-block rounded bg-muted px-2 py-1 text-[11px] font-bold uppercase text-muted-foreground">
          {alert.status}
        </p>
        {alert.level === "high" && (
          <p className="mt-3 flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            Mức nghiêm trọng: hãy liên hệ người thân hoặc bác sĩ ngay.
          </p>
        )}
      </section>

      {dose && (
        <section className="surface-card space-y-4 p-5">
          <div>
            <h2 className="text-sm font-bold uppercase text-muted-foreground">Liều liên quan</h2>
            <div className="mt-2 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-semibold">
                  {dose.time} · {dose.med}
                </p>
                <p className="truncate text-sm text-muted-foreground">{dose.strength}</p>
              </div>
              <span className="shrink-0 rounded-full bg-secondary px-2.5 py-1 text-[11px] font-bold text-secondary-foreground">
                {statusLabel[dose.status]}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Button
              onClick={() => {
                respondDose(dose.id, true);
                toast.success("Đã ghi nhận, hãy gửi ảnh để xác thực");
                router.push("/patient/family");
              }}
            >
              <Check className="mr-1 h-4 w-4" /> Đã uống
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                respondDose(dose.id, false);
                remindAgain(dose.id);
                toast("Sẽ nhắc lại sau 15 phút");
                router.push("/patient/family");
              }}
            >
              <X className="mr-1 h-4 w-4" /> Chưa uống
            </Button>
          </div>

          {!dose.photo && (
            <Button
              variant="outline"
              className="w-full"
              onClick={() => {
                sendPhoto(dose.id);
                toast.success("Ảnh đã gửi, AI đang đối chiếu");
                router.push("/patient/family");
              }}
            >
              <Camera className="mr-1 h-4 w-4" /> Gửi ảnh chụp thuốc
            </Button>
          )}

          <Button
            variant="ghost"
            className="w-full"
            onClick={() => {
              remindAgain(dose.id);
              toast("Đã nhắc lại");
            }}
          >
            <Clock className="mr-1 h-4 w-4" /> Nhắc lại sau
          </Button>
        </section>
      )}
    </div>
  );
}
