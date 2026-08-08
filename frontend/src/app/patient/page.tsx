"use client";

import { useState } from "react";
import { Camera, Check, CheckCircle2, Clock, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useProto, statusLabel } from "@/lib/proto-store";

export default function PatientToday() {
  const { doses, respondDose, sendPhoto, remindAgain, markMissed } = useProto();
  const [openId, setOpenId] = useState<string | null>(
    doses.find((d) => d.status === "pending")?.id ?? null,
  );
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
              Bạn đã uống thuốc chưa? Khung an toàn còn ±30 phút. Đã nhắc {next.reminders} lần.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <Button
                size="lg"
                onClick={() => {
                  respondDose(next.id, true);
                  setOpenId(next.id);
                  toast.success("Đã ghi nhận, hãy gửi ảnh để xác thực");
                }}
              >
                <Check className="mr-1 h-4 w-4" /> Đã uống
              </Button>
              <Button
                size="lg"
                variant="outline"
                onClick={() => {
                  respondDose(next.id, false);
                  remindAgain(next.id);
                  toast("Sẽ nhắc lại sau 15 phút");
                }}
              >
                <X className="mr-1 h-4 w-4" /> Chưa uống
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Button variant="ghost" size="sm" onClick={() => remindAgain(next.id)}>
                <Clock className="mr-1 h-4 w-4" /> Nhắc lại
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive"
                onClick={() => {
                  markMissed(next.id);
                  toast.error("Hết dose window — đã báo người thân");
                }}
              >
                Hết dose window
              </Button>
            </div>
          </div>
        </section>
      ) : (
        <section className="surface-card p-6 text-center">
          <CheckCircle2 className="mx-auto h-10 w-10 text-success" />
          <p className="mt-3 font-bold">Hôm nay bạn đã xử lý hết các liều</p>
          <p className="text-sm text-muted-foreground">Chúng tôi sẽ nhắc bạn ở liều tiếp theo.</p>
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

            {(d.status === "unverified" || openId === d.id) && !d.photo && (
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
