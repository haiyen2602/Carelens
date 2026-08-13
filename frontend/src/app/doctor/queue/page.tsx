"use client";

import {
  AlertTriangle,
  Calendar,
  Check,
  ChevronDown,
  ChevronUp,
  PencilLine,
  Pill,
  Repeat,
  StickyNote,
  X,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PrescriptionEditDialog } from "@/components/prescription-edit-dialog";
import { useProto, type Prescription } from "@/lib/proto-store";

function formatDate(iso: string) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

function durationLabel(p: Prescription) {
  if (!p.endDate) return `Từ ${formatDate(p.startDate)} · dài hạn`;
  return `${formatDate(p.startDate)} – ${formatDate(p.endDate)}`;
}

type Order = {
  orderId: string;
  patient: string;
  note: string;
  status: Prescription["status"];
  meds: Prescription[];
};

function groupOrders(list: Prescription[]): Order[] {
  const map = new Map<string, Order>();
  for (const p of list) {
    const existing = map.get(p.orderId);
    if (existing) {
      existing.meds.push(p);
    } else {
      map.set(p.orderId, {
        orderId: p.orderId,
        patient: p.patient,
        note: p.note,
        status: p.status,
        meds: [p],
      });
    }
  }
  return [...map.values()];
}

export default function QueuePage() {
  const { prescriptions, patients, decidePrescription, updatePrescription } = useProto();
  const [openId, setOpenId] = useState<string | null>(null);
  const [editingOrder, setEditingOrder] = useState<Order | null>(null);
  // Khoa theo orderId dang cho ket qua Duyet/Tu choi - decidePrescription chi
  // can id CUA MOT dong trong don (xem comment o proto-store.tsx) vi duyet/tu
  // choi 1 dong la duyet/tu choi CA phac do that dang sau no.
  const [dangXuLy, setDangXuLy] = useState<string | null>(null);
  const pendingOrders = groupOrders(prescriptions.filter((p) => p.status === "pending"));
  const doneOrders = groupOrders(prescriptions.filter((p) => p.status !== "pending"));
  const patientIdByName = new Map(
    patients.map((p, i) => [p.name, `BN${String(i + 1).padStart(4, "0")}`]),
  );

  const toggleOpen = (orderId: string) => {
    setOpenId((cur) => (cur === orderId ? null : orderId));
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Hàng đợi duyệt (HITL)</h1>
        <p className="text-sm text-muted-foreground">
          {pendingOrders.length} đơn thuốc (
          {prescriptions.filter((p) => p.status === "pending").length} thuốc) chờ quyết định của
          bác sĩ.
        </p>
      </header>

      {pendingOrders.length === 0 && (
        <div className="surface-card p-10 text-center">
          <p className="font-semibold">Hiện không có đơn nào chờ duyệt</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Kê đơn mới ở mục "Kê đơn thuốc" để thấy nó xuất hiện tại đây.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {pendingOrders.map((order) => {
          const isOpen = openId === order.orderId;
          const aiNote = order.meds.find((m) => m.note.startsWith("Đề xuất AI"))?.note;
          return (
            <div key={order.orderId} className="surface-card p-5">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4">
                <div className="min-w-0">
                  <p className="truncate text-lg font-bold">
                    {order.patient}
                    {patientIdByName.has(order.patient) && (
                      <span className="ml-2 text-sm font-normal text-muted-foreground">
                        ID: {patientIdByName.get(order.patient)}
                      </span>
                    )}
                  </p>
                  <p className="truncate text-sm text-muted-foreground">
                    {order.meds.map((m) => m.med || "(chưa đặt tên thuốc)").join(", ")}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Đơn thuốc gồm {order.meds.length} thuốc
                    {aiNote && " · có đề xuất AI cần xem"}
                  </p>
                </div>
                <span className="shrink-0 rounded-full bg-warning/25 px-3 py-1 text-xs font-bold text-warning-foreground">
                  Chờ duyệt
                </span>
              </div>

              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => toggleOpen(order.orderId)}
              >
                {isOpen ? (
                  <ChevronUp className="mr-1 h-4 w-4" />
                ) : (
                  <ChevronDown className="mr-1 h-4 w-4" />
                )}
                {isOpen ? "Ẩn chi tiết" : "Xem chi tiết"}
              </Button>

              {isOpen && (
                <div className="mt-4 space-y-4 border-t border-border pt-4">
                  {aiNote && (
                    <div className="flex gap-2 rounded-lg bg-warning/15 p-3 text-sm">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning-foreground" />
                      <span>{aiNote}</span>
                    </div>
                  )}

                  <div className="space-y-3">
                    {order.meds.map((m) => (
                      <div key={m.id} className="rounded-lg border border-border p-3">
                        <p className="flex items-center gap-1.5 font-semibold">
                          <Pill className="h-4 w-4 shrink-0 text-primary" /> {m.med}
                        </p>
                        <p className="mt-0.5 text-sm text-muted-foreground">
                          {m.dose} · {m.perDay} lần/ngày · {m.meal}
                        </p>

                        <div className="mt-2 flex flex-wrap gap-2">
                          {m.times.map((t) => (
                            <span
                              key={t}
                              className="rounded-lg bg-secondary px-3 py-1.5 font-mono text-sm"
                            >
                              {t} <span className="text-xs text-muted-foreground">±30′</span>
                            </span>
                          ))}
                        </div>

                        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1.5">
                            <Calendar className="h-3.5 w-3.5 shrink-0" /> {durationLabel(m)}
                          </span>
                          {m.cycle && (
                            <span className="flex items-center gap-1.5">
                              <Repeat className="h-3.5 w-3.5 shrink-0" /> Uống {m.cycle.onDays}{" "}
                              ngày, nghỉ {m.cycle.offDays} ngày
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {order.note && (
                    <div className="flex gap-2 rounded-lg bg-muted p-3 text-sm text-muted-foreground">
                      <StickyNote className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>{order.note}</span>
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2">
                    <Button
                      disabled={dangXuLy === order.orderId}
                      onClick={async () => {
                        setDangXuLy(order.orderId);
                        try {
                          await decidePrescription(order.meds[0].id, true);
                          toast.success(
                            `Đã duyệt & kích hoạt ${order.meds.length} thuốc, thông báo bệnh nhân + người thân`,
                          );
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Không duyệt được đơn thuốc");
                        } finally {
                          setDangXuLy(null);
                        }
                      }}
                    >
                      <Check className="mr-1 h-4 w-4" /> Duyệt cả đơn
                    </Button>
                    <Button variant="outline" onClick={() => setEditingOrder(order)}>
                      <PencilLine className="mr-1 h-4 w-4" /> Điều chỉnh thủ công
                    </Button>
                    <Button
                      variant="ghost"
                      className="text-destructive"
                      disabled={dangXuLy === order.orderId}
                      onClick={async () => {
                        setDangXuLy(order.orderId);
                        try {
                          await decidePrescription(order.meds[0].id, false);
                          toast("Đã từ chối đơn thuốc");
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Không từ chối được đơn thuốc");
                        } finally {
                          setDangXuLy(null);
                        }
                      }}
                    >
                      <X className="mr-1 h-4 w-4" /> Từ chối cả đơn
                    </Button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {doneOrders.length > 0 && (
        <section className="surface-card p-5">
          <h2 className="font-bold">Đã xử lý</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {doneOrders.map((order) => (
              <li key={order.orderId} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate">
                  {order.meds.map((m) => m.med).join(", ")} — {order.patient}
                  {patientIdByName.has(order.patient) && ` (${patientIdByName.get(order.patient)})`}
                </span>
                <span
                  className={`shrink-0 text-xs font-bold ${
                    order.status === "approved" ? "text-success" : "text-destructive"
                  }`}
                >
                  {order.status === "approved" ? "ĐÃ DUYỆT" : "TỪ CHỐI"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {editingOrder && (
        <PrescriptionEditDialog
          open={editingOrder !== null}
          onOpenChange={(o) => {
            if (!o) setEditingOrder(null);
          }}
          meds={editingOrder.meds}
          patient={editingOrder.patient}
          onSave={(rows) => {
            for (const row of rows) {
              updatePrescription(row.id, {
                med: row.med,
                dose: row.dose,
                perDay: row.perDay,
                meal: row.meal,
                times: row.times,
                startDate: row.startDate,
                endDate: row.endDate,
                cycle: row.hasCycle ? { onDays: row.cycleOnDays, offDays: row.cycleOffDays } : null,
              });
            }
            toast.success("Đã lưu điều chỉnh thủ công");
          }}
        />
      )}
    </div>
  );
}
