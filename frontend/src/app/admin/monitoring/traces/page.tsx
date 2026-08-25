"use client";

// BUILD-36: real server-side paginated/filtered Trace Explorer -- replaces
// the legacy /admin/rag "Trace Explorer" tab's browser alert() popup and
// hardcoded ring-buffer caps (see BUILD-36 report's own audit).

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { listTraces, type MonitoringFiltersInput, type TraceListOut } from "@/lib/admin-monitoring";

const PAGE_SIZE = 50;

export default function TraceExplorerPage() {
  const { accessToken } = useAuth();
  const [filters, setFilters] = useState<MonitoringFiltersInput>({});
  const [page, setPage] = useState(0);
  const [data, setData] = useState<TraceListOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      setData(await listTraces(filters, { limit: PAGE_SIZE, offset: page * PAGE_SIZE, accessToken }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi không xác định");
    } finally {
      setLoading(false);
    }
  }, [filters, page, accessToken]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Trace Explorer</h1>
        <p className="text-sm text-muted-foreground">Nguồn dữ liệu durable (agent_run) -- luôn có metric thật kể cả sau restart; nội dung câu hỏi/trả lời chỉ có khi trace còn trong buffer 200 mục gần nhất.</p>
      </div>

      <div className="surface-card flex flex-wrap items-end gap-3 p-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Status</label>
          <select className="rounded border bg-background px-2 py-1 text-sm" value={filters.status ?? "all"} onChange={(e) => { setPage(0); setFilters({ ...filters, status: e.target.value === "all" ? undefined : e.target.value }); }}>
            <option value="all">Tất cả</option>
            {["COMPLETED", "FAILED", "TIMEOUT", "BUDGET_EXCEEDED", "SAFETY_BLOCKED", "HANDOFF_REQUIRED", "HANDOFF_CREATED", "CANCELLED"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Error code</label>
          <input className="rounded border bg-background px-2 py-1 text-sm" value={filters.errorCode ?? ""} onChange={(e) => { setPage(0); setFilters({ ...filters, errorCode: e.target.value || undefined }); }} />
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải...
        </div>
      )}
      {error && (
        <div className="surface-card flex items-center gap-2 border-destructive/40 p-4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}
      {!loading && !error && data && (
        <div className="surface-card overflow-x-auto p-4">
          {data.items.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Chưa có trace nào khớp bộ lọc.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1">Trace</th><th>Path</th><th>Status</th><th>Bắt đầu</th><th>Duration (ms)</th><th>Đánh dấu</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.agent_run_id} className="border-t hover:bg-accent/40">
                    <td className="py-1">
                      {item.trace_id ? (
                        <Link className="font-mono text-xs text-primary underline" href={`/admin/monitoring/traces/${item.trace_id}`}>
                          {item.trace_id.slice(0, 8)}
                        </Link>
                      ) : (
                        <span className="text-xs text-muted-foreground">N/A</span>
                      )}
                    </td>
                    <td className="text-xs">{item.execution_path ?? "N/A"}</td>
                    <td className="text-xs">{item.status}{item.error_code ? ` (${item.error_code})` : ""}</td>
                    <td className="text-xs">{item.started_at ? new Date(item.started_at).toLocaleString("vi-VN") : "N/A"}</td>
                    <td className="text-xs">{item.duration_ms ?? "N/A"}</td>
                    <td className="flex gap-1 text-xs">
                      {item.has_ticket && <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-600">ticket</span>}
                      {item.has_safety_event && <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-rose-600">safety</span>}
                      {item.has_judge_result && <span className="rounded bg-violet-500/10 px-1.5 py-0.5 text-violet-600">judge</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
            <span>{data.total} trace -- trang {page + 1}/{totalPages}</span>
            <div className="flex gap-2">
              <button type="button" disabled={page === 0} className="rounded border px-2 py-1 disabled:opacity-40" onClick={() => setPage((p) => Math.max(0, p - 1))}>Trước</button>
              <button type="button" disabled={page + 1 >= totalPages} className="rounded border px-2 py-1 disabled:opacity-40" onClick={() => setPage((p) => p + 1)}>Sau</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
