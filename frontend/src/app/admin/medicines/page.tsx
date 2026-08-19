"use client";

import { AlertCircle, AlertTriangle, CheckCircle2, Loader2, Search, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MEDICINES, type MedicineEntry, type MedicineStatus } from "@/lib/admin-mock";

const statusMeta: Record<
  MedicineStatus,
  { label: string; tone: string; icon: typeof CheckCircle2 }
> = {
  indexed: { label: "Đã index", tone: "bg-success/15 text-success", icon: CheckCircle2 },
  processing: { label: "Đang xử lý", tone: "bg-primary/10 text-primary", icon: Loader2 },
  error: {
    label: "Lỗi — cần xem lại",
    tone: "bg-destructive/12 text-destructive",
    icon: AlertCircle,
  },
};

export default function MedicinesPage() {
  const [items, setItems] = useState<MedicineEntry[]>(MEDICINES);
  const [q, setQ] = useState("");
  const [importing, setImporting] = useState(false);

  const list = useMemo(
    () =>
      items.filter(
        (m) =>
          m.name.toLowerCase().includes(q.toLowerCase()) ||
          m.activeIngredient.toLowerCase().includes(q.toLowerCase()),
      ),
    [items, q],
  );

  const reindex = (id: string) => {
    setItems((prev) => prev.map((m) => (m.id === id ? { ...m, status: "processing" } : m)));
    setTimeout(() => {
      setItems((prev) =>
        prev.map((m) =>
          m.id === id
            ? { ...m, status: "indexed", updatedAt: "Vừa xong", version: bumpVersion(m.version) }
            : m,
        ),
      );
    }, 1400);
  };

  const simulateImport = () => {
    setImporting(true);
    setTimeout(() => setImporting(false), 1600);
  };

  const indexed = items.filter((m) => m.status === "indexed").length;

  return (
    <div className="space-y-6">
      <header className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
        <p className="min-w-0 text-sm text-muted-foreground">
          {indexed}/{items.length} bản ghi đã index · nguồn tri thức cho agent trả lời câu hỏi về
          thuốc.
        </p>
        <Button onClick={simulateImport} disabled={importing}>
          {importing ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <Upload className="mr-1 h-4 w-4" />
          )}
          {importing ? "Đang nạp dữ liệu..." : "Nạp dữ liệu mới"}
        </Button>
      </header>

      <div className="flex items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/10 p-4">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <p className="text-sm text-destructive">
          <span className="font-bold">Dữ liệu minh hoạ (mock)</span> — danh sách và trạng thái bên
          dưới là dữ liệu mẫu cố định. "Index lại"/"Nạp dữ liệu mới" chỉ giả lập bằng hẹn giờ, chưa
          gọi API thật — chưa thay đổi nguồn tri thức thật mà agent dùng để trả lời.
        </p>
      </div>

      <div className="relative max-w-md">
        <Search
          aria-hidden="true"
          className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Tìm theo tên thuốc, hoạt chất..."
          aria-label="Tìm theo tên thuốc hoặc hoạt chất"
          className="pl-9"
        />
      </div>

      <div className="surface-card overflow-x-auto">
        <table className="w-full min-w-[880px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/60 text-left text-xs font-semibold text-muted-foreground">
              <th className="px-4 py-3">Tên thuốc</th>
              <th className="px-4 py-3">Hoạt chất</th>
              <th className="px-4 py-3">Nhóm</th>
              <th className="px-4 py-3">Nguồn</th>
              <th className="px-4 py-3">Phiên bản</th>
              <th className="px-4 py-3">Cập nhật</th>
              <th className="px-4 py-3">Trạng thái</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {list.map((m) => {
              const meta = statusMeta[m.status];
              const Icon = meta.icon;
              return (
                <tr key={m.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-semibold">{m.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{m.activeIngredient}</td>
                  <td className="px-4 py-3">{m.category}</td>
                  <td className="px-4 py-3 text-muted-foreground">{m.source}</td>
                  <td className="px-4 py-3 font-mono text-xs">{m.version}</td>
                  <td className="px-4 py-3 text-muted-foreground">{m.updatedAt}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold ${meta.tone}`}
                    >
                      <Icon
                        className={`h-3.5 w-3.5 ${m.status === "processing" ? "animate-spin" : ""}`}
                      />
                      {meta.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={m.status === "processing"}
                      onClick={() => reindex(m.id)}
                    >
                      {m.status === "error" ? "Thử lại" : "Index lại"}
                    </Button>
                  </td>
                </tr>
              );
            })}
            {list.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                  Không tìm thấy dữ liệu thuốc phù hợp.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function bumpVersion(v: string) {
  const n = parseInt(v.replace("v", ""), 10) || 1;
  return `v${n + 1}`;
}
