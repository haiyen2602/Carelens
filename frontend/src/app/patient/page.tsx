"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Camera, CheckCircle2, Smile, ThumbsUp, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useProto, statusLabel } from "@/lib/proto-store";

export default function PatientToday() {
  const router = useRouter();
  const {
    doses,
    respondDose,
    sendPhoto,
    remindAgain,
    markMissed,
    reportHealth,
    requestSymptomCheck,
  } = useProto();
  const [checkinDone, setCheckinDone] = useState(false);
  const next = doses.find((d) => d.status === "pending");

  return (
    <div className="space-y-4">
      {next ? (
        <section className="surface-card overflow-hidden">
          <div className="brand-gradient p-5 text-primary-foreground">
            <p className="text-sm opacity-85">Đến giờ uống thuốc</p>
            <p className="text-4xl font-extrabold">{next.time}</p>
            <p className="mt-1 text-sm opacity-90">{next.meal}</p>
          </div>
          <div className="space-y-4 p-5">
            <div>
              <p className="text-lg font-bold">{next.med}</p>
              <p className="text-sm text-muted-foreground">{next.strength}</p>
            </div>
            <p className="rounded-lg bg-accent p-3 text-sm text-accent-foreground">
              Hãy chụp ảnh thuốc để xác nhận đã uống. Khung an toàn còn ±30 phút. Đã nhắc{" "}
              {next.reminders} lần.
            </p>
            <Button
              size="lg"
              className="w-full"
              onClick={() => {
                sendPhoto(next.id);
                toast.success("Ảnh đã gửi, AI đang đối chiếu — ghi nhận ĐÃ UỐNG");
              }}
            >
              <Camera className="mr-1 h-4 w-4" /> Chụp ảnh xác nhận đã uống
            </Button>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => {
                respondDose(next.id, false);
                if (next.reminders >= 1) {
                  markMissed(next.id);
                  toast.error("Đã nhắc tối đa 2 lần (30 phút) — ghi nhận BỎ LIỀU");
                } else {
                  remindAgain(next.id);
                  toast("Sẽ nhắc lại sau 15 phút");
                }
              }}
            >
              <X className="mr-1 h-4 w-4" /> Chưa uống
            </Button>
          </div>
        </section>
      ) : checkinDone ? (
        <section className="surface-card p-6 text-center">
          <CheckCircle2 className="mx-auto h-10 w-10 text-success" />
          <p className="mt-3 font-bold">Hôm nay bạn đã xử lý hết các liều</p>
          <p className="text-sm text-muted-foreground">Chúng tôi sẽ nhắc bạn ở liều tiếp theo.</p>
        </section>
      ) : (
        <section className="surface-card p-5 text-center">
          <Smile className="mx-auto h-10 w-10 text-primary" />
          <h1 className="mt-3 text-xl font-extrabold">Hôm nay bạn thấy thế nào?</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Câu trả lời giúp bác sĩ và người thân theo dõi tình trạng của bạn.
          </p>
          <div className="mt-5 space-y-3">
            <Button
              className="w-full"
              size="lg"
              onClick={() => {
                reportHealth("Bình thường", "low");
                toast.success("Đã ghi nhận: bình thường");
                setCheckinDone(true);
              }}
            >
              <ThumbsUp className="mr-1 h-4 w-4" /> Bình thường
            </Button>
            <Button
              variant="outline"
              className="w-full"
              size="lg"
              onClick={() => {
                requestSymptomCheck();
                router.push("/patient/assistant");
              }}
            >
              <AlertTriangle className="mr-1 h-4 w-4" /> Không ổn
            </Button>
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-bold uppercase text-muted-foreground">
          Thời khóa biểu hôm nay
        </h2>
        {doses.map((d) => (
          <div key={d.id} className="surface-card p-4">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
              <div className="min-w-0">
                <p className="truncate font-semibold">
                  {d.time} · {d.med}
                </p>
                <p className="truncate text-sm text-muted-foreground">
                  {d.strength} · {d.meal}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${
                  d.status === "taken"
                    ? "bg-success/15 text-success"
                    : d.status === "missed" || d.status === "wrong"
                      ? "bg-destructive/15 text-destructive"
                      : d.status === "unverified"
                        ? "bg-warning/25 text-warning-foreground"
                        : "bg-secondary text-secondary-foreground"
                }`}
              >
                {statusLabel[d.status]}
              </span>
            </div>

            {d.status === "unverified" && !d.photo && (
              <Button
                variant="outline"
                className="mt-3 w-full"
                onClick={() => {
                  sendPhoto(d.id);
                  toast.success("Ảnh đã gửi, AI đang đối chiếu");
                }}
              >
                <Camera className="mr-1 h-4 w-4" /> Gửi ảnh chụp thuốc
              </Button>
            )}
            {d.note && <p className="mt-2 text-xs text-warning-foreground">{d.note}</p>}
          </div>
        ))}
      </section>
    </div>
  );
}
