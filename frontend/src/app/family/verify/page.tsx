"use client";

import { Camera, Check, EyeOff, UserX, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useProto } from "@/lib/proto-store";

export default function VerifyPage() {
  const { doses, verifyDose } = useProto();
  const queue = doses.filter((d) => d.status === "unverified");

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold">Hàng đợi duyệt ảnh</h1>
      {queue.length === 0 && (
        <p className="surface-card p-6 text-center text-sm text-muted-foreground">
          Không còn ảnh nào cần đối chiếu.
        </p>
      )}
      {queue.map((d) => (
        <section key={d.id} className="surface-card overflow-hidden">
          <div className="grid h-44 place-items-center bg-muted text-muted-foreground">
            <div className="text-center">
              <Camera className="mx-auto h-8 w-8" />
              <p className="mt-2 text-xs">Ảnh chụp thuốc bệnh nhân gửi lúc {d.time}</p>
            </div>
          </div>
          <div className="space-y-3 p-4">
            <div>
              <p className="font-bold">
                {d.med} · {d.strength}
              </p>
              <p className="text-sm text-muted-foreground">
                Liều {d.time} · {d.meal} · nhắc {d.reminders} lần
              </p>
            </div>
            {d.note && <p className="rounded-lg bg-warning/15 p-3 text-xs">{d.note}</p>}
            <div className="grid grid-cols-2 gap-2">
              <Button
                size="sm"
                onClick={() => {
                  verifyDose(d.id, "correct");
                  toast.success("TAKEN — đã xác nhận đúng thuốc");
                }}
              >
                <Check className="mr-1 h-4 w-4" /> Đúng thuốc
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-destructive"
                onClick={() => {
                  verifyDose(d.id, "wrong");
                  toast.error("WRONG — đã chuyển bác sĩ xem xét");
                }}
              >
                <X className="mr-1 h-4 w-4" /> Sai thuốc
              </Button>
              <Button size="sm" variant="ghost" onClick={() => verifyDose(d.id, "unclear")}>
                <EyeOff className="mr-1 h-4 w-4" /> Không nhìn rõ
              </Button>
              <Button size="sm" variant="ghost" onClick={() => verifyDose(d.id, "absent")}>
                <UserX className="mr-1 h-4 w-4" /> Không có mặt
              </Button>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
