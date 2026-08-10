"use client";

import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useProto, statusLabel } from "@/lib/proto-store";

export default function FamilyHistory() {
  const { doses, patients, toggleWatch } = useProto();
  const problems = doses.filter((d) => ["wrong", "missed", "unverified"].includes(d.status));
  const lan = patients[0];

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold">Lịch sử uống sai</h1>
      {problems.length === 0 && (
        <p className="surface-card p-6 text-center text-sm text-muted-foreground">
          Chưa ghi nhận lỗi liều nào.
        </p>
      )}
      {problems.map((d) => (
        <section key={d.id} className="surface-card p-4">
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
            <div className="min-w-0">
              <p className="truncate font-semibold">
                {d.time} · {d.med}
              </p>
              <p className="text-sm text-muted-foreground">
                {d.status === "wrong"
                  ? "Sai thuốc"
                  : d.status === "missed"
                    ? "Thiếu liều"
                    : "Chưa xác thực"}
              </p>
            </div>
            <span className="shrink-0 text-xs font-bold text-destructive">
              {statusLabel[d.status]}
            </span>
          </div>
        </section>
      ))}

      {lan && (
        <section className="surface-card space-y-3 p-4">
          <p className="font-semibold">Danh sách theo dõi</p>
          <p className="text-sm text-muted-foreground">
            {lan.name}{" "}
            {lan.watch ? "đang trong danh sách theo dõi sát." : "chưa được theo dõi sát."}
          </p>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => {
              toggleWatch(lan.id);
              toast.success(
                lan.watch ? "Đã bỏ khỏi danh sách theo dõi" : "Đã đưa vào danh sách theo dõi",
              );
            }}
          >
            {lan.watch ? "Bỏ theo dõi" : "Đưa vào danh sách theo dõi"}
          </Button>
        </section>
      )}
    </div>
  );
}
