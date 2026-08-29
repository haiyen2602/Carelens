"use client";

// BUILD-36: real server-side paginated/filtered Trace Explorer -- replaces
// the legacy /admin/rag "Trace Explorer" tab's browser alert() popup and
// hardcoded ring-buffer caps (see BUILD-36 report's own audit).

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, useTransition } from "react";
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Database,
  Info,
  LayoutDashboard,
  ListChecks,
  ListFilter,
  Loader2,
  RotateCcw,
  ShieldAlert,
  Ticket,
} from "lucide-react";
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

const EXECUTION_PATH_METADATA: Record<string, { label: string; description: string }> = {
  DRUG_LOOKUP: {
    label: "Tra cứu thông tin thuốc",
    description: "Tra cứu chi tiết chỉ định, liều dùng, tác dụng phụ và chống chỉ định từ cơ sở dữ liệu dược học.",
  },
  DETERMINISTIC_TOOL: {
    label: "Công cụ tính toán nghiệp vụ",
    description: "Thực thi công cụ quy chuẩn xác định (tính liều lượng, lịch nhắc uống thuốc, chuyển đổi đơn vị).",
  },
  DETERMINISTIC_SCHEDULE: {
    label: "Lập lịch uống thuốc",
    description: "Xử lý và thiết lập lịch nhắc uống thuốc tự động theo phác đồ điều trị.",
  },
  GENERAL_MODEL: {
    label: "Mô hình ngôn ngữ tổng quát",
    description: "Xử lý hội thoại tự nhiên, giải thích thông tin y tế thông thường không cần gọi công cụ đặc thù.",
  },
  RAG: {
    label: "Truy xuất tài liệu y khoa (RAG)",
    description: "Tìm kiếm và tổng hợp thông tin từ cơ sở tri thức y dược và tài liệu chuyên môn.",
  },
  TRIAGE: {
    label: "Phân loại triệu chứng",
    description: "Đánh giá mức độ khẩn cấp của triệu chứng và đưa ra hướng xử trí ban đầu.",
  },
  MEDICATION_DOSE_SAFETY: {
    label: "Kiểm tra an toàn liều lượng",
    description: "Kiểm tra an toàn liều dùng, tương tác thuốc và cảnh báo nguy cơ vượt liều.",
  },
  SAFETY: {
    label: "Bộ lọc an toàn y khoa",
    description: "Kích hoạt quy tắc an toàn bảo vệ bệnh nhân và chặn các nội dung vi phạm tiêu chuẩn y tế.",
  },
  HANDOFF: {
    label: "Chuyển tiếp bác sĩ",
    description: "Tạo phiếu hỗ trợ và chuyển giao ca bệnh phức tạp sang hàng đợi bác sĩ chuyên môn.",
  },
  FALLBACK: {
    label: "Phản hồi dự phòng",
    description: "Kích hoạt phản hồi an toàn dự phòng khi hệ thống gặp ngoại lệ hoặc sự cố kết nối.",
  },
  OUT_OF_SCOPE: {
    label: "Ngoài phạm vi hỗ trợ",
    description: "Yêu cầu nằm ngoài phạm vi tư vấn y tế hoặc năng lực phục vụ của hệ thống.",
  },
};

const TRACE_STATUS_METADATA: Record<string, { label: string; bgClass: string }> = {
  COMPLETED: { label: "Thành công", bgClass: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20" },
  HANDOFF_CREATED: { label: "Chuyển tiếp bác sĩ", bgClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20" },
  HANDOFF_REQUIRED: { label: "Cần chuyển bác sĩ", bgClass: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20" },
  SAFETY_BLOCKED: { label: "Chặn vi phạm an toàn", bgClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20" },
  BUDGET_EXCEEDED: { label: "Vượt ngân sách", bgClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20" },
  TIMEOUT: { label: "Hết thời gian chờ", bgClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20" },
  FAILED: { label: "Thất bại", bgClass: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20" },
  CANCELLED: { label: "Đã hủy", bgClass: "bg-muted text-muted-foreground border" },
};

const ERROR_CODE_METADATA: Record<string, string> = {
  GROUNDING_FAILURE: "Lỗi thiếu căn cứ",
  BUDGET_EXCEEDED: "Vượt ngân sách",
  TIMEOUT: "Hết thời gian chờ",
  SAFETY_BLOCKED: "Bị chặn an toàn",
  RETRIEVAL_EMPTY: "Truy xuất rỗng",
  TOOL_EXECUTION_ERROR: "Lỗi thực thi công cụ",
  LLM_API_ERROR: "Lỗi gọi API Model",
  INTERNAL_ERROR: "Lỗi nội bộ",
};

export default function TraceExplorerPage() {
  const { accessToken } = useAuth();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const urlStatus = searchParams.get("status") || undefined;
  const urlErrorCode = searchParams.get("error_code") || undefined;
  const urlExecutionPath = searchParams.get("execution_path") || undefined;
  const urlPageStr = searchParams.get("page");
  const urlPage = urlPageStr ? Math.max(0, parseInt(urlPageStr, 10) - 1) : 0;

  const [status, setStatus] = useState<string | undefined>(urlStatus);
  const [errorCode, setErrorCode] = useState<string | undefined>(urlErrorCode);
  const [executionPath, setExecutionPath] = useState<string | undefined>(urlExecutionPath);
  const [page, setPage] = useState<number>(urlPage);
  const [versionOptions, setVersionOptions] = useState<VersionFiltersOut | null>(null);

  const [data, setData] = useState<TraceListOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    getVersionFilters(accessToken).then(setVersionOptions).catch(() => {});
  }, [accessToken]);

  // Sync state from URL changes (when clicking browser back/forward)
  useEffect(() => {
    setStatus(urlStatus);
    setErrorCode(urlErrorCode);
    setExecutionPath(urlExecutionPath);
    setPage(urlPage);
  }, [urlStatus, urlErrorCode, urlPage, urlExecutionPath]);

  const updateUrl = useCallback(
    (newStatus?: string, newErrorCode?: string, newPath?: string, newPage: number = 0) => {
      const sp = new URLSearchParams();
      if (newStatus && newStatus !== "all") sp.set("status", newStatus);
      if (newErrorCode && newErrorCode.trim()) sp.set("error_code", newErrorCode.trim());
      if (newPath && newPath !== "all") sp.set("execution_path", newPath);
      if (newPage > 0) sp.set("page", String(newPage + 1));
      const query = sp.toString() ? `?${sp.toString()}` : "";
      startTransition(() => {
        router.push(`/admin/monitoring/traces${query}`);
      });
    },
    [router]
  );

  const fetchData = useCallback(async (isBackground: boolean = false) => {
    if (!accessToken) return;
    if (!isBackground && !data) setLoading(true);
    setIsRefreshing(true);
    setError(null);
    try {
      const filterInput: MonitoringFiltersInput = {
        status: status && status !== "all" ? status : undefined,
        errorCode: errorCode && errorCode.trim() ? errorCode.trim() : undefined,
        executionPath: executionPath && executionPath !== "all" ? executionPath : undefined,
      };
      setData(await listTraces(filterInput, { limit: PAGE_SIZE, offset: page * PAGE_SIZE, accessToken }));
    } catch (e) {
      if (!data) {
        setError(e instanceof Error ? e.message : "Lỗi không xác định");
      }
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [status, errorCode, executionPath, page, accessToken, data]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const handleStatusChange = (newStatus: string) => {
    const s = newStatus === "all" ? undefined : newStatus;
    setStatus(s);
    setPage(0);
    updateUrl(s, errorCode, executionPath, 0);
  };

  const handleErrorCodeChange = (newCode: string) => {
    const c = newCode || undefined;
    setErrorCode(c);
    setPage(0);
    updateUrl(status, c, executionPath, 0);
  };

  const handleExecutionPathChange = (newPath: string) => {
    const p = newPath === "all" ? undefined : newPath;
    setExecutionPath(p);
    setPage(0);
    updateUrl(status, errorCode, p, 0);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    updateUrl(status, errorCode, executionPath, newPage);
  };

  const resetFilters = () => {
    setStatus(undefined);
    setErrorCode(undefined);
    setExecutionPath(undefined);
    setPage(0);
    updateUrl(undefined, undefined, undefined, 0);
  };

  const availableErrorCodes = Array.from(
    new Set([
      ...STANDARD_ERROR_CODES,
      ...(versionOptions?.error_code ?? []),
      ...(errorCode ? [errorCode] : []),
    ])
  );

  const availablePaths = Array.from(
    new Set([
      "DRUG_LOOKUP",
      "DETERMINISTIC_TOOL",
      "DETERMINISTIC_SCHEDULE",
      "GENERAL_MODEL",
      "RAG",
      "TRIAGE",
      "MEDICATION_DOSE_SAFETY",
      "SAFETY",
      "HANDOFF",
      "FALLBACK",
      ...(versionOptions?.execution_path ?? []),
    ])
  );

  const { intervalMs, setIntervalMs, lastRefreshedAt, isPollingActive } = useMonitoringPolling({
    defaultIntervalMs: 10000,
    onUpdate: () => {
      fetchData(true);
      if (accessToken) {
        getVersionFilters(accessToken).then(setVersionOptions).catch(() => {});
      }
    },
  });

  const activeFilterCount = [status, errorCode, executionPath].filter(Boolean).length;

  return (
    <div className="space-y-5 pb-10">
      {/* Header & Navigation */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <Link href="/admin/monitoring">
              <Button variant="outline" size="sm" className="h-8 text-xs">
                <ArrowLeft className="mr-1 h-3.5 w-3.5" /> Bảng điều khiển Giám sát
              </Button>
            </Link>
            <h1 className="text-xl font-bold tracking-tight">Trình khám phá dấu vết</h1>
            <div className="flex items-center gap-2 ml-2">
              <div className="flex items-center gap-1.5 rounded-lg border bg-background px-2.5 py-1 text-xs shadow-sm">
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
        </div>
        <button
          type="button"
          onClick={() => fetchData(false)}
          className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-accent h-8 shadow-sm"
        >
          <RotateCcw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
          Làm mới
        </button>
      </div>

      {/* Filter Section */}
      <div className="surface-card flex flex-wrap items-end gap-3 p-4 border border-border/70 shadow-sm rounded-xl">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Trạng thái xử lý</label>
          <select
            className="rounded-lg border bg-background px-2.5 py-1 text-sm h-8 min-w-[170px] focus:ring-1 focus:ring-primary focus:outline-none cursor-pointer"
            value={status ?? "all"}
            onChange={(e) => handleStatusChange(e.target.value)}
          >
            <option value="all">Tất cả trạng thái</option>
            {Object.entries(TRACE_STATUS_METADATA).map(([key, meta]) => (
              <option key={key} value={key}>
                {meta.label} ({key})
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Đường dẫn xử lý</label>
          <select
            className="rounded-lg border bg-background px-2.5 py-1 text-sm h-8 min-w-[190px] focus:ring-1 focus:ring-primary focus:outline-none cursor-pointer"
            value={executionPath ?? "all"}
            onChange={(e) => handleExecutionPathChange(e.target.value)}
          >
            <option value="all">Tất cả đường dẫn</option>
            {availablePaths.map((p) => {
              const meta = EXECUTION_PATH_METADATA[p];
              return (
                <option key={p} value={p}>
                  {meta?.label ? `${meta.label} (${p})` : p}
                </option>
              );
            })}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">Mã lỗi</label>
          <select
            className="rounded-lg border bg-background px-2.5 py-1 text-sm h-8 min-w-[180px] focus:ring-1 focus:ring-primary focus:outline-none cursor-pointer"
            value={errorCode ?? "all"}
            onChange={(e) => handleErrorCodeChange(e.target.value === "all" ? "" : e.target.value)}
          >
            <option value="all">Tất cả mã lỗi</option>
            {availableErrorCodes.map((c) => (
              <option key={c} value={c}>
                {ERROR_CODE_METADATA[c] ? `${ERROR_CODE_METADATA[c]} (${c})` : c}
              </option>
            ))}
          </select>
        </div>

        {activeFilterCount > 0 && (
          <button
            type="button"
            onClick={resetFilters}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition-colors shadow-sm h-8"
          >
            <RotateCcw className="h-3 w-3" /> Đặt lại bộ lọc ({activeFilterCount})
          </button>
        )}
      </div>

      {loading && !data && (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin text-primary" /> Đang tải danh sách trace...
        </div>
      )}

      {error && !data && (
        <div className="surface-card flex items-center gap-2 border-destructive/40 p-4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      {data && (
        <div className="surface-card overflow-hidden rounded-xl border border-border/80 shadow-sm">
          <div className="p-4 border-b flex items-center justify-between flex-wrap gap-2">
            <div>
              <h3 className="font-bold text-sm">Danh sách Trace thực tế</h3>
              <p className="text-xs text-muted-foreground">
                Tổng số: {data.total.toLocaleString("vi-VN")} trace (Hiển thị trang {page + 1}/{totalPages})
              </p>
            </div>
          </div>

          {data.items.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              Không có trace nào khớp với điều kiện lọc hiện tại.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] text-sm text-left">
                <thead>
                  <tr className="border-b bg-muted/50 text-xs text-muted-foreground">
                    <th className="py-3 px-4">Mã Trace</th>
                    <th className="py-3 px-4">Đường dẫn xử lý</th>
                    <th className="py-3 px-4">Trạng thái</th>
                    <th className="py-3 px-4">Thời gian bắt đầu</th>
                    <th className="py-3 px-4 text-right">Độ trễ</th>
                    <th className="py-3 px-4 text-center">Đánh dấu</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.items.map((item) => {
                    const pathKey = item.execution_path ?? "";
                    const pathMeta = EXECUTION_PATH_METADATA[pathKey];
                    const statusMeta = TRACE_STATUS_METADATA[item.status] ?? {
                      label: item.status,
                      bgClass: item.status.includes("FAILED") || item.status.includes("TIMEOUT") || item.status.includes("EXCEEDED")
                        ? "bg-rose-500/10 text-rose-600 border-rose-500/20"
                        : item.status.includes("HANDOFF") || item.status.includes("SAFETY")
                        ? "bg-amber-500/10 text-amber-600 border-amber-500/20"
                        : "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
                    };

                    const durationDisplay =
                      item.duration_ms !== null && item.duration_ms !== undefined
                        ? item.duration_ms < 1
                          ? "< 1 ms"
                          : `${Math.round(item.duration_ms).toLocaleString("vi-VN")} ms`
                        : "—";

                    return (
                      <tr key={item.agent_run_id} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 px-4">
                          {item.trace_id ? (
                            <Link
                              className="font-mono text-xs font-bold text-primary underline hover:text-primary/80"
                              href={`/admin/monitoring/traces/${item.trace_id}`}
                            >
                              {item.trace_id.slice(0, 8)}
                            </Link>
                          ) : (
                            <span className="text-xs text-muted-foreground">N/A</span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex flex-col" title={pathMeta?.description}>
                            <span className="font-medium text-foreground text-xs">{pathMeta?.label ?? pathKey}</span>
                            {pathKey && <span className="font-mono text-[11px] text-muted-foreground">{pathKey}</span>}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusMeta.bgClass}`}>
                              {statusMeta.label}
                            </span>
                            {item.error_code && (
                              <span className="inline-flex rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-mono text-rose-600">
                                {item.error_code}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-xs text-muted-foreground">
                          {item.started_at
                            ? new Date(item.started_at).toLocaleString("vi-VN", {
                                timeZone: "Asia/Ho_Chi_Minh",
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                                day: "2-digit",
                                month: "2-digit",
                                year: "numeric",
                              })
                            : "N/A"}
                        </td>
                        <td className="py-3 px-4 text-right font-medium text-xs text-foreground">
                          {durationDisplay}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center justify-center gap-1.5 flex-wrap">
                            {item.has_judge_result && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-violet-500/10 text-violet-700 dark:text-violet-400 border border-violet-500/20 px-2 py-0.5 text-[11px] font-medium">
                                <ListChecks className="h-3 w-3" /> Judge
                              </span>
                            )}
                            {item.has_safety_event && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-500/20 px-2 py-0.5 text-[11px] font-medium">
                                <ShieldAlert className="h-3 w-3" /> An toàn
                              </span>
                            )}
                            {item.has_ticket && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20 px-2 py-0.5 text-[11px] font-medium">
                                <Ticket className="h-3 w-3" /> Ticket
                              </span>
                            )}
                            {!item.has_judge_result && !item.has_safety_event && !item.has_ticket && (
                              <span className="text-muted-foreground text-xs">—</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          <div className="p-4 border-t flex items-center justify-between text-xs text-muted-foreground flex-wrap gap-2 bg-muted/20">
            <span>
              Tổng số <strong>{data.total.toLocaleString("vi-VN")}</strong> trace • Trang <strong>{page + 1}</strong> / <strong>{totalPages}</strong>
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                className="h-8 text-xs gap-1"
                onClick={() => handlePageChange(Math.max(0, page - 1))}
              >
                <ChevronLeft className="h-3.5 w-3.5" /> Trang trước
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page + 1 >= totalPages}
                className="h-8 text-xs gap-1"
                onClick={() => handlePageChange(page + 1)}
              >
                Trang sau <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
