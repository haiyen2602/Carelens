"use client";

import { AlertTriangle, Check, PencilLine, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useProto } from "@/lib/proto-store";

export default function QueuePage() {
  const { prescriptions, decidePrescription } = useProto();
  const [editing, setEditing] = useState<string | null>(null);
  // Id (co dang "{prescId}::{idx}") dang cho ket qua Duyet/Tu choi - khoa
  // dung DONG do lai, khong khoa ca danh sach: mot phac do nhieu thuoc rai
  // thanh nhieu dong, duyet 1 dong la duyet CA phac do, nen cac dong con lai
  // cua CUNG phac do van bam duoc trong luc cho - backend tu chan trung
  // (409 INVALID_STATE) neu co ai lo bam lan hai.
  const [dangXuLy, setDangXuLy] = useState<string | null>(null);
  const pending = prescriptions.filter((p) => p.status === "pending");
  const done = prescriptions.filter((p) => p.status !== "pending");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Hàng đợi duyệt (HITL)</h1>
        <p className="text-sm text-muted-foreground">
          {pending.length} phác đồ chờ quyết định của bác sĩ.
        </p>
      </header>

      {pending.length === 0 && (
        <div className="surface-card p-10 text-center">
          <p className="font-semibold">Hiện không có mục nào chờ duyệt</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Kê đơn mới ở mục “Kê đơn thuốc” để thấy nó xuất hiện tại đây.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {pending.map((p) => (
          <div key={p.id} className="surface-card p-5">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4">
              <div className="min-w-0">
                <p className="truncate text-lg font-bold">{p.med}</p>
                <p className="text-sm text-muted-foreground">
                  {p.patient} · {p.dose} · {p.perDay} lần/ngày · {p.meal}
                </p>
              </div>
              <span className="shrink-0 rounded-full bg-warning/25 px-3 py-1 text-xs font-bold text-warning-foreground">
                Chờ duyệt
              </span>
            </div>

            {p.note.startsWith("Đề xuất AI") && (
              <div className="mt-4 flex gap-2 rounded-lg bg-warning/15 p-3 text-sm">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning-foreground" />
                <span>{p.note}</span>
              </div>
            )}

            <div className="mt-4">
              <p className="text-xs font-semibold uppercase text-muted-foreground">
                Timeline đề xuất
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {p.times.map((t) => (
                  <span key={t} className="rounded-lg bg-secondary px-3 py-1.5 font-mono text-sm">
                    {t} <span className="text-xs text-muted-foreground">±30′</span>
                  </span>
                ))}
              </div>
            </div>

            {editing === p.id && (
              <div className="mt-4 grid gap-3 rounded-lg bg-muted p-4 sm:grid-cols-2">
                <Input defaultValue={p.times.join(", ")} placeholder="Giờ uống" />
                <Input defaultValue={p.dose} placeholder="Liều" />
                <p className="text-xs text-muted-foreground sm:col-span-2">
                  Điều chỉnh thủ công — thay đổi sẽ được ghi vào audit log khi duyệt.
                </p>
              </div>
            )}

            <div className="mt-5 flex flex-wrap gap-2">
              <Button
                disabled={dangXuLy === p.id}
                onClick={async () => {
                  setDangXuLy(p.id);
                  try {
                    await decidePrescription(p.id, true);
                    toast.success("Đã duyệt & kích hoạt phác đồ, thông báo bệnh nhân + người thân");
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : "Không duyệt được phác đồ");
                  } finally {
                    setDangXuLy(null);
                  }
                }}
              >
                <Check className="mr-1 h-4 w-4" /> Duyệt
              </Button>
              <Button variant="outline" onClick={() => setEditing(editing === p.id ? null : p.id)}>
                <PencilLine className="mr-1 h-4 w-4" /> Điều chỉnh thủ công
              </Button>
              <Button
                variant="ghost"
                className="text-destructive"
                disabled={dangXuLy === p.id}
                onClick={async () => {
                  setDangXuLy(p.id);
                  try {
                    await decidePrescription(p.id, false);
                    toast("Đã từ chối phác đồ");
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : "Không từ chối được phác đồ");
                  } finally {
                    setDangXuLy(null);
                  }
                }}
              >
                <X className="mr-1 h-4 w-4" /> Từ chối
              </Button>
            </div>
          </div>
        ))}
      </div>

      {done.length > 0 && (
        <section className="surface-card p-5">
          <h2 className="font-bold">Đã xử lý</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {done.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate">
                  {p.med} — {p.patient}
                </span>
                <span
                  className={`shrink-0 text-xs font-bold ${
                    p.status === "approved" ? "text-success" : "text-destructive"
                  }`}
                >
                  {p.status === "approved" ? "ĐÃ DUYỆT" : "TỪ CHỐI"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
