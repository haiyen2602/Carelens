"use client";

// BUILD-36: real server-side paginated/filtered Trace Explorer -- replaces
// the legacy /admin/rag "Trace Explorer" tab's browser alert() popup and
// hardcoded ring-buffer caps (see BUILD-36 report's own audit).

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, useTransition } from "react";
import { AlertCircle, ArrowLeft, LayoutDashboard, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useMonitoringPolling, POLLING_OPTIONS, type PollingIntervalOption } from "@/hooks/use-monitoring-polling";
import { getVersionFilters, listTraces, type MonitoringFiltersInput, type TraceListOut, type VersionFiltersOut } from "@/lib/admin-monitoring";

const PAGE_SIZE = 50;

const STANDARD_ERROR_CODES = [
  "GROUNDING_FAILURE",
  "BUDGET_EXCEEDED",
  "TIMEOUT",
  "SAFETY_BLOCKED",
  "RETRIEVAL_EMPTY",
  "TOOL_EXECUTION_ERROR",
  "LLM_API_ERROR",
  "INTERNAL_ERROR",
];

export default function TraceExplorerPage() {
  const { accessToken } = useAuth();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const urlStatus = searchParams.get("status") || undefined;
  const urlErrorCode = searchParams.get("error_code") || undefined;
  const urlPageStr = searchParams.get("page");
  const urlPage = urlPageStr ? Math.max(0, parseInt(urlPageStr, 10) - 1) : 0;

  const [status, setStatus] = useState<string | undefined>(urlStatus);
  const [errorCode, setErrorCode] = useState<string | undefined>(urlErrorCode);
  const [page, setPage] = useState<number>(urlPage);
  const [versionOptions, setVersionOptions] = useState<VersionFiltersOut | null>(null);

  const [data, setData] = useState<TraceListOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    getVersionFilters(accessToken).then(setVersionOptions).catch(() => {});
  }, [accessToken]);

  // Sync state from URL changes (when clicking browser back/forward)
  useEffect(() => {
    setStatus(urlStatus);
    setErrorCode(urlErrorCode);
    setPage(urlPage);
  }, [urlStatus, urlErrorCode, urlPage]);

  const updateUrl = useCallback(
    (newStatus?: string, newErrorCode?: string, newPage: number = 0) => {
      const sp = new URLSearchParams();
      if (newStatus && newStatus !== "all") sp.set("status", newStatus);
      if (newErrorCode && newErrorCode.trim()) sp.set("error_code", newErrorCode.trim());
      if (newPage > 0) sp.set("page", String(newPage + 1));
      const query = sp.toString() ? `?${sp.toString()}` : "";
      startTransition(() => {
        router.push(`/admin/monitoring/traces${query}`);
      });
    },
    [router]
  );

  const fetchData = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const filterInput: MonitoringFiltersInput = {
        status: status && status !== "all" ? status : undefined,
        errorCode: errorCode && errorCode.trim() ? errorCode.trim() : undefined,
      };
      setData(await listTraces(filterInput, { limit: PAGE_SIZE, offset: page * PAGE_SIZE, accessToken }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi không xác định");
    } finally {
      setLoading(false);
    }
  }, [status, errorCode, page, accessToken]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const handleStatusChange = (newStatus: string) => {
    const s = newStatus === "all" ? undefined : newStatus;
    setStatus(s);
    setPage(0);
    updateUrl(s, errorCode, 0);
  };

  const handleErrorCodeChange = (newCode: string) => {
    const c = newCode || undefined;
    setErrorCode(c);
    setPage(0);
    updateUrl(status, c, 0);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    updateUrl(status, errorCode, newPage);
  };

  const resetFilters = () => {
    setStatus(undefined);
    setErrorCode(undefined);
    setPage(0);
    updateUrl(undefined, undefined, 0);
  };

  const availableErrorCodes = Array.from(
    new Set([
      ...STANDARD_ERROR_CODES,
      ...(versionOptions?.error_code ?? []),
      ...(errorCode ? [errorCode] : []),
    ])
  );

  const { intervalMs, setIntervalMs, lastRefreshedAt, isPollingActive, triggerUpdate } = useMonitoringPolling({
    defaultIntervalMs: 10000,
    onUpdate: () => {
      fetchData();
      if (accessToken) {
        getVersionFilters(accessToken).then(setVersionOptions).catch(() => {});
      }
    },
  });

  return (
    <div className="space-y-4">
      {/* Header & Back to dashboard */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <Link href="/admin/monitoring">
              <Button variant="outline" size="sm" className="h-8 text-xs">
                <ArrowLeft className="mr-1 h-3.5 w-3.5" /> Bảng điều khiển Giám sát
              </Button>
            </Link>
            <h1 className="text-xl font-semibold">Trace Explorer</h1>
            <div className="flex items-center gap-2 ml-2">
              <div className="flex items-center gap-1.5 rounded border bg-background px-2 py-1 text-xs">
                <span
                  className={`h-2 w-2 rounded-full ${
                    isPollingActive ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/50"
                  }`}
                />
                <select
                  value={intervalMs}
                  onChange={(e) => setIntervalMs(Number(e.target.value) as PollingIntervalOption)}
                  className="bg-transparent text-xs font-medium focus:outline-none cursor-pointer"
                  title="Tần suất tự động làm mới dữ liệu"
                >
                  {POLLING_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              {isPollingActive && (
                <span className="text-[11px] text-muted-foreground hidden sm:inline">
                  (Cập nhật {lastRefreshedAt.toLocaleTimeString()})
                </span>
              )}
            </div>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Nguồn dữ liệu durable (agent_run) -- luôn có metric thật kể cả sau restart; nội dung câu hỏi/trả lời chỉ có khi trace còn trong buffer 200 mục gần nhất.
          </p>
        </div>
        <button
          type="button"
          onClick={triggerUpdate}
          className="flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs hover:bg-accent h-8"
        >
          <RotateCcw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Làm mới
        </button>
      </div>

      <div className="surface-card flex flex-wrap items-end gap-3 p-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Trạng thái (Status)</label>
          <select
            className="rounded border bg-background px-2.5 py-1 text-sm h-8"
            value={status ?? "all"}
            onChange={(e) => handleStatusChange(e.target.value)}
          >
            <option value="all">Tất cả trạng thái</option>
            {["COMPLETED", "FAILED", "TIMEOUT", "BUDGET_EXCEEDED", "SAFETY_BLOCKED", "HANDOFF_REQUIRED", "HANDOFF_CREATED", "CANCELLED"].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Mã lỗi (Error Code)</label>
          <select
            className="rounded border bg-background px-2.5 py-1 text-sm h-8 min-w-[180px]"
            value={errorCode ?? "all"}
            onChange={(e) => handleErrorCodeChange(e.target.value === "all" ? "" : e.target.value)}
          >
            <option value="all">Tất cả mã lỗi</option>
            {availableErrorCodes.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        {(status || errorCode || page > 0) && (
          <Button variant="ghost" size="sm" onClick={resetFilters} className="h-8 text-xs text-muted-foreground">
            Đặt lại bộ lọc
          </Button>
        )}
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
              <button
                type="button"
                disabled={page === 0}
                className="rounded border px-2.5 py-1 disabled:opacity-40 hover:bg-accent"
                onClick={() => handlePageChange(Math.max(0, page - 1))}
              >
                Trước
              </button>
              <button
                type="button"
                disabled={page + 1 >= totalPages}
                className="rounded border px-2.5 py-1 disabled:opacity-40 hover:bg-accent"
                onClick={() => handlePageChange(page + 1)}
              >
                Sau
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
