"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Database,
  DollarSign,
  ExternalLink,
  FileSearch,
  Filter,
  Gauge,
  Info,
  Layers,
  ListChecks,
  Loader2,
  RefreshCw,
  RotateCcw,
  ScrollText,
  Search,
  Server,
  ShieldAlert,
  Sparkles,
  Trophy,
  Zap,
} from "lucide-react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  PieChart,
  Pie,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { useAuth } from "@/lib/auth";
import { useMonitoringPolling, POLLING_OPTIONS, type PollingIntervalOption } from "@/hooks/use-monitoring-polling";
import {
  compareVersions,
  getCost,
  getErrors,
  getGolden,
  getJudge,
  getOverview,
  getPerformance,
  getQuality,
  getRetrieval,
  getSafetyEvents,
  getSafetySummary,
  getTrend,
  getVersionFilters,
  type CompareOut,
  type CostOut,
  type ErrorsOut,
  type GoldenOut,
  type JudgeOut,
  type MetricValue,
  type MonitoringFiltersInput,
  type OverviewOut,
  type PerformanceOut,
  type QualityOut,
  type RetrievalOut,
  type TrendOut,
  type VersionFiltersOut,
} from "@/lib/admin-monitoring";

// ─── Types ───────────────────────────────────────────────────────────────────

type TabId =
  | "overview"
  | "quality"
  | "retrieval"
  | "safety"
  | "performance"
  | "cost"
  | "errors";

const TABS: { id: TabId; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "Tổng quan", icon: Activity },
  { id: "quality", label: "Chất lượng AI & RAG", icon: Sparkles },
  { id: "retrieval", label: "Truy xuất", icon: ScrollText },
  { id: "safety", label: "An toàn & Chuyển bác sĩ", icon: ShieldAlert },
  { id: "performance", label: "Hiệu năng & Độ trễ", icon: Gauge },
  { id: "cost", label: "Token & Chi phí", icon: DollarSign },
  { id: "errors", label: "Phân tích lỗi", icon: AlertCircle },
];

// ─── Thresholds ───────────────────────────────────────────────────────────────

const THRESHOLDS = {
  faithfulness: { warn: 0.75, error: 0.6, target: 0.85 },
  answer_relevance: { warn: 0.70, error: 0.55, target: 0.80 },
  success_rate: { warn: 0.85, error: 0.80, target: 0.90 },
  error_rate: { warn: 0.10, error: 0.15, target: 0.05 },
  p95_latency_ms: { warn: 5000, error: 8000, target: 3000 },
  grounding_failure_rate: { warn: 0.05, error: 0.10, target: 0.03 },
};

// ─── Formatters ───────────────────────────────────────────────────────────────

function formatMetric(
  m: MetricValue | undefined,
  opts: { percent?: boolean; suffix?: string; integer?: boolean; currency?: boolean } = {}
): string {
  if (!m || m.value === null || m.value === undefined || m.status !== "AVAILABLE")
    return "N/A";
  if (typeof m.value === "string" && Number.isNaN(Number(m.value))) {
    return `${m.value}${opts.suffix ?? ""}`;
  }
  const v = typeof m.value === "number" ? m.value : Number(m.value);
  if (Number.isNaN(v)) return "N/A";
  if (opts.percent) return `${(v * 100).toFixed(1)}%`;
  if (opts.integer) return `${Math.round(v).toLocaleString("vi-VN")}${opts.suffix ?? ""}`;
  if (opts.currency) {
    const formatted = v < 0.0001 && v > 0 ? "< $0.0001" : `$${v.toFixed(v < 0.01 ? 4 : 3)}`;
    return `${formatted}${opts.suffix ?? ""}`;
  }
  return `${v.toFixed(v < 10 ? 3 : 2)}${opts.suffix ?? ""}`;
}

function metricColor(
  key: keyof typeof THRESHOLDS,
  val: number | null | undefined
): string {
  if (val === null || val === undefined) return "text-muted-foreground";
  const t = THRESHOLDS[key];
  if (!t) return "text-foreground";
  // For "higher is better" metrics
  if (key !== "error_rate" && key !== "p95_latency_ms" && key !== "grounding_failure_rate") {
    if (val < t.error) return "text-rose-600";
    if (val < t.warn) return "text-amber-600";
    return "text-emerald-600";
  }
  // For "lower is better" metrics
  if (val > t.error) return "text-rose-600";
  if (val > t.warn) return "text-amber-600";
  return "text-emerald-600";
}

// ─── Human-friendly note mapper ───────────────────────────────────────────────

const TECHNICAL_NOTE_MAP: Record<string, string> = {
  in_memory_ring_buffer_current_process_only: "Bộ nhớ đệm (phiên chạy hiện tại)",
  in_memory_ring_buffer_current_process_only_never_made_durable: "Bộ nhớ đệm tạm thời",
  NOT_APPLICABLE: "Chưa áp dụng cho phiên này",
  NOT_AVAILABLE: "Chưa có dữ liệu ghi nhận",
  NO_RUN_PERSISTED_YET: "Chưa có lượt đánh giá nào được lưu",
  no_stable_retrieval_id_contract_see_build_31_and_build_35: "Chưa hỗ trợ ID truy xuất cố định",
  grounding_failure_spans_multiple_intents_not_isolable_to_rag_only_today_see_grounding_failure_rate:
    "Xem tỷ lệ Grounding Failure bên cạnh",
  never_emitted_by_current_runtime_no_per_tool_or_per_retrieval_deadline_distinct_from_run_timeout:
    "Chưa ghi nhận trong phiên bản hiện tại",
};

function formatHumanNote(raw?: string | null): string | null {
  if (!raw) return null;
  if (TECHNICAL_NOTE_MAP[raw]) return TECHNICAL_NOTE_MAP[raw];
  if (raw.includes("in_memory_ring_buffer")) return "Bộ nhớ đệm (phiên hiện tại)";
  if (raw.includes("no_stable_retrieval_id")) return "Chưa hỗ trợ ID truy xuất cố định";
  if (raw.includes("grounding_failure")) return "Xem tỷ lệ Grounding Failure";
  return raw;
}

// ─── Small shared components ──────────────────────────────────────────────────

function MetricTypeBadge({ type }: { type?: MetricValue["metric_type"] }) {
  if (!type) return null;
  const tone: Record<string, string> = {
    LIVE: "bg-emerald-500/10 text-emerald-700 border-emerald-200",
    GOLDEN: "bg-amber-500/10 text-amber-700 border-amber-200",
    HEURISTIC: "bg-sky-500/10 text-sky-700 border-sky-200",
    LLM_JUDGE: "bg-violet-500/10 text-violet-700 border-violet-200",
    DETERMINISTIC: "bg-slate-500/10 text-slate-700 border-slate-200",
  };
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${tone[type] ?? "bg-muted"}`}>
      {type}
    </span>
  );
}

function MetricCard({
  label,
  metric,
  percent,
  suffix,
  integer,
  currency,
  help,
  sub,
  thresholdKey,
}: {
  label: string;
  metric?: MetricValue;
  percent?: boolean;
  suffix?: string;
  integer?: boolean;
  currency?: boolean;
  help?: string;
  sub?: string;
  thresholdKey?: keyof typeof THRESHOLDS;
}) {
  const display = formatMetric(metric, { percent, suffix, integer, currency });
  const numVal = metric?.status === "AVAILABLE" && typeof metric.value === "number" ? metric.value : null;
  const colorClass = thresholdKey && numVal !== null ? metricColor(thresholdKey, numVal) : "text-foreground";
  const noteText = formatHumanNote(metric?.scope ?? metric?.scope_note ?? metric?.note);
  const reasonOrStatus = formatHumanNote(metric?.reason ?? metric?.status);

  return (
    <div className="surface-card p-4" title={help}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{label}</p>
        <MetricTypeBadge type={metric?.metric_type} />
      </div>
      <p className={`mt-1 text-2xl font-semibold ${colorClass}`}>{display}</p>
      {metric && metric.status === "AVAILABLE" && metric.numerator != null && metric.denominator != null ? (
        <p className="mt-1 text-[11px] text-muted-foreground">
          {metric.numerator} / {metric.denominator}
          {metric.sample_count != null ? ` (n=${metric.sample_count})` : ""}
        </p>
      ) : metric && metric.status !== "AVAILABLE" ? (
        <p className="mt-1 text-[11px] text-muted-foreground">{reasonOrStatus}</p>
      ) : null}
      {noteText && (
        <p className="mt-1 text-[10px] italic text-muted-foreground">
          {noteText}
        </p>
      )}
      {sub && <p className="mt-1 text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

function AgentEvaluationCard({
  title,
  subtitle,
  metric,
  percent,
  suffix,
  valueOverride,
  colorScheme,
  thresholdKey,
}: {
  title: string;
  subtitle: string;
  metric?: MetricValue;
  percent?: boolean;
  suffix?: string;
  valueOverride?: string;
  colorScheme?: "emerald" | "rose" | "sky" | "amber";
  thresholdKey?: keyof typeof THRESHOLDS;
}) {
  const display = valueOverride ?? formatMetric(metric, { percent, suffix });
  const numVal = metric?.status === "AVAILABLE" && typeof metric.value === "number" ? metric.value : null;

  let valueColor = "text-emerald-600";
  if (colorScheme === "rose") valueColor = "text-rose-600";
  else if (colorScheme === "sky") valueColor = "text-sky-600";
  else if (colorScheme === "amber") valueColor = "text-amber-600";
  else if (thresholdKey && numVal !== null) {
    valueColor = metricColor(thresholdKey, numVal);
  }

  return (
    <div className="surface-card p-5 flex flex-col justify-between hover:shadow-md transition-shadow">
      <div>
        <h4 className="text-sm font-bold text-foreground tracking-tight">{title}</h4>
        <p className="text-xs text-muted-foreground mt-1 leading-snug">{subtitle}</p>
      </div>
      <div className="mt-4">
        <p className={`text-3xl font-extrabold tracking-tight ${valueColor}`}>{display}</p>
        {metric && metric.status === "AVAILABLE" && metric.numerator != null && metric.denominator != null && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            {metric.numerator} / {metric.denominator}
            {metric.sample_count != null ? ` (n=${metric.sample_count})` : ""}
          </p>
        )}
      </div>
    </div>
  );
}

/** Card for metrics that are permanently N/A due to architectural limits */
function DisabledMetricCard({
  label, reason, technicalNote,
}: {
  label: string;
  reason: string;
  technicalNote?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="surface-card p-4 opacity-60">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{label}</p>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
          title={technicalNote}
        >
          <Info className="h-3 w-3" />
          {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
      </div>
      <p className="mt-1 text-sm font-medium text-muted-foreground italic">Chưa hỗ trợ phiên này</p>
      {open && (
        <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
          {reason}
          {technicalNote && <span className="block mt-0.5 opacity-70">{technicalNote}</span>}
        </p>
      )}
    </div>
  );
}

/** Warning banner shown when a metric is below threshold */
function WarningBanner({
  label,
  value,
  target,
  unit = "%",
  drillLabel,
  onDrill,
  href,
}: {
  label: string;
  value: number;
  target: number;
  unit?: string;
  drillTab?: TabId;
  drillLabel?: string;
  onDrill?: () => void;
  href?: string;
}) {
  const pct = unit === "%" ? (value * 100).toFixed(1) : value.toFixed(0);
  const targetPct = unit === "%" ? (target * 100).toFixed(0) : target.toFixed(0);
  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
      <div className="flex-1">
        <span className="font-semibold">{label}</span> hiện ở mức{" "}
        <span className="font-bold">{pct}{unit}</span>, dưới mục tiêu{" "}
        <span className="font-semibold">{targetPct}{unit}</span>.
      </div>
      {href ? (
        <Link
          href={href}
          className="text-xs font-semibold text-amber-800 underline hover:text-amber-950 cursor-pointer whitespace-nowrap"
        >
          {drillLabel || "Xem chi tiết"} →
        </Link>
      ) : onDrill && drillLabel ? (
        <button
          type="button"
          onClick={onDrill}
          className="text-xs font-semibold text-amber-800 underline hover:text-amber-950 cursor-pointer whitespace-nowrap bg-transparent border-0 p-0"
        >
          {drillLabel} →
        </button>
      ) : drillLabel ? (
        <span className="text-xs font-medium text-amber-700 whitespace-nowrap">
          {drillLabel}
        </span>
      ) : null}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" /> Đang tải dữ liệu...
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="surface-card flex items-center gap-2 border-destructive/40 p-4 text-sm text-destructive">
      <AlertCircle className="h-4 w-4" /> {message}
    </div>
  );
}

function UnavailableState({ reason }: { reason?: string }) {
  const formattedReason = formatHumanNote(reason);
  return (
    <div className="surface-card p-4 text-sm text-muted-foreground">
      Dữ liệu hiện không khả dụng{formattedReason ? ` (${formattedReason})` : ""}. Không phải 0 — xem lại sau.
    </div>
  );
}

const ERROR_CODE_METADATA: Record<string, { label: string; description: string }> = {
  BUDGET_EXCEEDED: {
    label: "Vượt giới hạn Token / Chi phí",
    description: "Số lượng token hoặc số bước gọi mô hình/công cụ vượt quá giới hạn ngân sách an toàn cho mỗi lượt xử lý.",
  },
  GROUNDING_FAILURE: {
    label: "Lỗi kiểm chứng thông tin (Grounding)",
    description: "Câu trả lời của AI không đủ bằng chứng đối chiếu từ tài liệu y khoa được truy xuất (chặn nguy cơ ảo giác/hallucination).",
  },
  TOOL_ERROR: {
    label: "Lỗi thực thi công cụ",
    description: "Công cụ nghiệp vụ (tra cứu phác đồ, tính liều, lịch uống) gặp ngoại lệ hoặc trả về dữ liệu sai cấu trúc.",
  },
  TOOL_TIMEOUT: {
    label: "Quá thời gian chờ công cụ",
    description: "Thời gian thực thi công cụ vượt quá ngưỡng timeout cho phép (chưa ghi nhận phát sinh trong phiên bản hiện tại).",
  },
  MODEL_ERROR: {
    label: "Lỗi phản hồi mô hình AI",
    description: "Mô hình AI trả về lỗi API (HTTP 5xx, rate limit 429 hoặc lỗi dịch vụ từ nhà cung cấp LLM).",
  },
  MODEL_TIMEOUT: {
    label: "Quá thời gian chờ mô hình AI",
    description: "Thời gian phản hồi từ mô hình AI vượt quá ngưỡng timeout cấu hình.",
  },
  RETRIEVAL_ERROR: {
    label: "Lỗi truy xuất tài liệu (RAG)",
    description: "Quá trình tìm kiếm vector/full-text trên cơ sở dữ liệu dược học gặp sự cố kết nối hoặc lỗi truy vấn.",
  },
  RETRIEVAL_TIMEOUT: {
    label: "Quá thời gian truy xuất tài liệu",
    description: "Quá trình tìm kiếm tài liệu tham khảo vượt quá thời gian phản hồi cho phép (chưa ghi nhận phát sinh trong phiên bản hiện tại).",
  },
  REQUEST_TIMEOUT: {
    label: "Quá thời gian toàn trình",
    description: "Toàn bộ quy trình xử lý chuỗi tác vụ của yêu cầu vượt quá ngưỡng thời gian tối đa.",
  },
  EMPTY_REPLY: {
    label: "Phản hồi rỗng",
    description: "Mô hình AI hoàn thành phiên xử lý nhưng không trả về bất kỳ nội dung văn bản nào.",
  },
  HANDOFF_FAILURE: {
    label: "Lỗi chuyển giao bác sĩ",
    description: "Quá trình tạo phiếu chuyển tiếp hoặc gửi ca sang hàng đợi bác sĩ chuyên môn gặp sự cố.",
  },
  INTERNAL_ERROR: {
    label: "Lỗi hệ thống nội bộ",
    description: "Lỗi ngoại lệ không xác định phát sinh trong luồng xử lý runtime của hệ thống.",
  },
  SAFETY_BLOCKED: {
    label: "Bị chặn bởi bộ lọc an toàn",
    description: "Yêu cầu bị chặn do vi phạm quy tắc an toàn y tế hoặc chứa nội dung không an toàn.",
  },
  RETRIEVAL_EMPTY: {
    label: "Truy xuất không có kết quả",
    description: "Không tìm thấy đoạn tài liệu y khoa nào phù hợp với câu hỏi trong cơ sở dữ liệu.",
  },
  TIMEOUT: {
    label: "Hết thời gian chờ (Timeout)",
    description: "Yêu cầu xử lý vượt quá thời gian timeout quy định.",
  },
};

function FilterBar({
  filters, setFilters, options,
}: {
  filters: MonitoringFiltersInput;
  setFilters: (f: MonitoringFiltersInput) => void;
  options: VersionFiltersOut | null;
}) {
  const set = (patch: Partial<MonitoringFiltersInput>) => setFilters({ ...filters, ...patch });
  const activeCount = [
    filters.dateFrom,
    filters.dateTo,
    filters.model,
    filters.promptVersion,
    filters.retrievalVersion,
    filters.executionPath,
    filters.errorCode,
    filters.judgeModel,
  ].filter(Boolean).length;

  return (
    <div className="surface-card flex flex-wrap items-end gap-3 p-4 border border-border/70 shadow-sm rounded-xl">
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">Từ ngày</label>
        <input
          type="date"
          className="rounded-lg border bg-background px-2.5 py-1 text-sm h-8 focus:ring-1 focus:ring-primary focus:outline-none"
          value={filters.dateFrom ?? ""}
          onChange={(e) => set({ dateFrom: e.target.value || undefined })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">Đến ngày</label>
        <input
          type="date"
          className="rounded-lg border bg-background px-2.5 py-1 text-sm h-8 focus:ring-1 focus:ring-primary focus:outline-none"
          value={filters.dateTo ?? ""}
          onChange={(e) => set({ dateTo: e.target.value || undefined })}
        />
      </div>
      <FilterSelect
        label="Mô hình AI"
        value={filters.model}
        options={options?.model ?? []}
        onChange={(v) => set({ model: v })}
      />
      <FilterSelect
        label="Phiên bản Prompt"
        value={filters.promptVersion}
        options={options?.prompt_version ?? []}
        onChange={(v) => set({ promptVersion: v })}
      />
      <FilterSelect
        label="Phiên bản Truy xuất"
        value={filters.retrievalVersion}
        options={options?.retrieval_version ?? []}
        onChange={(v) => set({ retrievalVersion: v })}
      />
      <FilterSelect
        label="Đường dẫn xử lý"
        value={filters.executionPath}
        options={options?.execution_path ?? []}
        displayMapper={(val) => EXECUTION_PATH_METADATA[val]?.label ? `${EXECUTION_PATH_METADATA[val].label} (${val})` : val}
        onChange={(v) => set({ executionPath: v })}
      />
      <FilterSelect
        label="Mã lỗi"
        value={filters.errorCode}
        options={options?.error_code ?? []}
        displayMapper={(val) => ERROR_CODE_METADATA[val]?.label ? `${ERROR_CODE_METADATA[val].label} (${val})` : val}
        onChange={(v) => set({ errorCode: v })}
      />
      <FilterSelect
        label="Mô hình Đánh giá (Judge)"
        value={filters.judgeModel}
        options={options?.judge_model ?? []}
        onChange={(v) => set({ judgeModel: v })}
      />
      {activeCount > 0 && (
        <button
          type="button"
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition-colors shadow-sm h-8"
          onClick={() => setFilters({})}
        >
          <RotateCcw className="h-3 w-3" /> Đặt lại bộ lọc ({activeCount})
        </button>
      )}
    </div>
  );
}

function FilterSelect({
  label, value, options, displayMapper, onChange,
}: {
  label: string;
  value?: string;
  options: string[];
  displayMapper?: (val: string) => string;
  onChange: (v: string | undefined) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <select
        className="rounded-lg border bg-background px-2.5 py-1 text-sm h-8 focus:ring-1 focus:ring-primary focus:outline-none cursor-pointer"
        value={value ?? "all"}
        onChange={(e) => onChange(e.target.value === "all" ? undefined : e.target.value)}
      >
        <option value="all">Tất cả</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {displayMapper ? displayMapper(o) : o}
          </option>
        ))}
      </select>
    </div>
  );
}

// ─── Chart Components ─────────────────────────────────────────────────────────

const CHART_COLORS = ["#2563eb", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];

function TrendChart({ data }: { data: TrendOut }) {
  if (!data.available || data.trend.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        Chưa có dữ liệu trend. Hãy thực hiện trò chuyện để ghi nhận.
      </div>
    );
  }
  const chartData = data.trend.map((p) => ({
    date: p.date.slice(5), // MM-DD
    task_completion: p.task_completion !== null && p.task_completion !== undefined ? Math.round(p.task_completion * 100) : null,
    faithfulness: p.faithfulness !== null ? Math.round(p.faithfulness * 100) : null,
    relevance: p.relevance !== null ? Math.round(p.relevance * 100) : null,
    task_n: p.task_completion_n ?? p.requests,
    faith_n: p.faithfulness_n,
    rel_n: p.relevance_n,
    requests: p.requests,
  }));
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="gTask" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#2563eb" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gFaith" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" stroke="var(--muted-foreground)" fontSize={11} />
          <YAxis
            domain={[0, 100]}
            stroke="var(--muted-foreground)"
            fontSize={11}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#fff",
              borderColor: "var(--border)",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            formatter={(val, name, props) => {
              const isTask = name === "task_completion" || String(name).includes("Task Completion");
              const n = isTask ? props.payload.task_n : props.payload.faith_n;
              const label = isTask
                ? "Tỷ lệ hoàn thành (Task Completion)"
                : "Độ trung thực (Faithfulness)";
              return [`${val}% (n=${n})`, label];
            }}
          />
          <Legend />
          <Area
            type="monotone"
            dataKey="task_completion"
            name="Tỷ lệ hoàn thành (Task Completion)"
            stroke="#2563eb"
            strokeWidth={2}
            fill="url(#gTask)"
            connectNulls
            dot={{ r: 3, fill: "#2563eb" }}
            activeDot={{ r: 5 }}
          />
          <Area
            type="monotone"
            dataKey="faithfulness"
            name="Độ trung thực (Faithfulness)"
            stroke="#10b981"
            strokeWidth={2}
            fill="url(#gFaith)"
            connectNulls
            dot={{ r: 3, fill: "#10b981" }}
            activeDot={{ r: 5 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function DonutChart({
  data,
  title,
}: {
  data: { name: string; value: number; color: string }[];
  title: string;
}) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return <div className="py-8 text-center text-xs text-muted-foreground">Chưa có dữ liệu</div>;
  return (
    <div>
      <p className="mb-2 text-xs font-semibold text-muted-foreground uppercase">{title}</p>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={48}
              outerRadius={72}
              paddingAngle={2}
              dataKey="value"
            >
              {data.map((entry, idx) => (
                <Cell key={idx} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(val, name) => [`${((val as number / total) * 100).toFixed(1)}% (${val})`, name]}
              contentStyle={{ fontSize: "12px", borderRadius: "8px" }}
            />
            <Legend iconType="circle" iconSize={8} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function HorizontalBarChart({
  data,
  title,
  valueFormatter,
}: {
  data: { label: string; value: number }[];
  title: string;
  valueFormatter?: (v: number) => string;
}) {
  if (data.length === 0) return null;
  const fmt = valueFormatter ?? ((v) => `${v}`);
  return (
    <div className="surface-card p-4">
      <p className="mb-3 text-sm font-semibold">{title}</p>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 0, bottom: 0 }}>
            <XAxis type="number" fontSize={11} stroke="var(--muted-foreground)" tickFormatter={fmt} />
            <YAxis type="category" dataKey="label" fontSize={11} stroke="var(--muted-foreground)" width={100} />
            <Tooltip
              formatter={(v) => fmt(v as number)}
              contentStyle={{ fontSize: "12px", borderRadius: "8px" }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {data.map((_, idx) => (
                <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function CostTimelineChart({
  timeline,
  models,
  title,
}: {
  timeline: Array<{ timestamp: string;[model: string]: number | string }>;
  models: string[];
  title: string;
}) {
  if (!timeline || timeline.length === 0 || !models || models.length === 0) {
    return (
      <div className="surface-card p-4 text-sm text-muted-foreground">
        Không có dữ liệu chuỗi thời gian chi phí cho bộ lọc hiện tại.
      </div>
    );
  }

  const formatTimeTick = (ts: string) => {
    if (!ts) return "";
    if (ts.includes(" ")) {
      const [datePart, timePart] = ts.split(" ");
      const [, m, d] = datePart.split("-");
      return `${timePart} ${d}/${m}`;
    }
    const [, m, d] = ts.split("-");
    return `${d}/${m}`;
  };

  return (
    <div className="surface-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold">{title}</p>
        <span className="text-xs text-muted-foreground">
          Trục hoành: Thời gian | Trục tung: Giá tiền ($ USD)
        </span>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={timeline} margin={{ left: 16, right: 24, top: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.5} />
            <XAxis
              dataKey="timestamp"
              fontSize={11}
              stroke="var(--muted-foreground)"
              tickFormatter={formatTimeTick}
            />
            <YAxis
              type="number"
              fontSize={11}
              stroke="var(--muted-foreground)"
              tickFormatter={(v) => `$${Number(v).toFixed(4)}`}
            />
            <Tooltip
              formatter={(v, name) => [`$${Number(v ?? 0).toFixed(4)}`, name]}
              labelFormatter={(label) => `Thời gian: ${label}`}
              contentStyle={{
                fontSize: "12px",
                borderRadius: "8px",
                backgroundColor: "var(--background)",
                borderColor: "var(--border)",
                color: "var(--foreground)",
              }}
            />
            <Legend iconType="circle" iconSize={8} />
            {models.map((modelName, idx) => (
              <Line
                key={modelName}
                type="monotone"
                dataKey={modelName}
                name={modelName}
                stroke={CHART_COLORS[idx % CHART_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── Tab: Overview ────────────────────────────────────────────────────────────

// ─── Tab: Overview ────────────────────────────────────────────────────────────

function OverviewTab({
  data,
  trend,
  trendDays,
  setTrendDays,
  judgeData,
  safety,
  onNavigateTab,
}: {
  data: OverviewOut;
  trend: TrendOut | null;
  trendDays: number;
  setTrendDays: (d: number) => void;
  judgeData: JudgeOut | null;
  safety: SafetySummary | null;
  onNavigateTab: (tab: TabId) => void;
}) {
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const successVal = data.success_rate?.status === "AVAILABLE" && typeof data.success_rate.value === "number"
    ? data.success_rate.value : null;
  const errorVal = data.error_rate?.status === "AVAILABLE" && typeof data.error_rate.value === "number"
    ? data.error_rate.value : null;

  // Format latency P95 (e.g., 5.2s p95 or 850ms p95)
  const p95Val = data.latency_p95_ms?.status === "AVAILABLE" && typeof data.latency_p95_ms.value === "number"
    ? data.latency_p95_ms.value
    : null;
  const latencyDisplay = p95Val !== null
    ? (p95Val >= 1000 ? `${(p95Val / 1000).toFixed(1)}s p95` : `${Math.round(p95Val)}ms p95`)
    : "N/A";

  // Format cost per task (e.g., $0.0012 or $0.185)
  const costVal = data.cost_per_query_usd?.status === "AVAILABLE" && typeof data.cost_per_query_usd.value === "number"
    ? data.cost_per_query_usd.value
    : null;
  const costDisplay = costVal !== null ? (costVal < 0.0001 && costVal > 0 ? "< $0.0001" : `$${costVal.toFixed(costVal < 0.01 ? 4 : 3)}`) : "N/A";

  // 5-bucket distribution for Judge scores (0.0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0)
  const judgeScoreDist = judgeData?.overall_score_distribution
    ? Object.entries(judgeData.overall_score_distribution).map(([name, value], idx) => ({
      name,
      value,
      color: ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"][idx % 5],
    }))
    : [
      { name: "0.0–0.2", value: 0, color: "#3b82f6" },
      { name: "0.2–0.4", value: 0, color: "#10b981" },
      { name: "0.4–0.6", value: 0, color: "#f59e0b" },
      { name: "0.6–0.8", value: 0, color: "#ef4444" },
      { name: "0.8–1.0", value: 0, color: "#8b5cf6" },
    ];

  return (
    <div className="space-y-6">
      {/* Warnings */}
      <div className="space-y-2">
        {successVal !== null && successVal < THRESHOLDS.success_rate.warn && (
          <WarningBanner
            label="Tỷ lệ hoàn thành tác vụ (Task Completion)"
            value={successVal}
            target={THRESHOLDS.success_rate.target}
            drillTab="errors"
            drillLabel="Xem phân tích lỗi"
            onDrill={() => onNavigateTab("errors")}
          />
        )}
        {errorVal !== null && errorVal > THRESHOLDS.error_rate.warn && (
          <WarningBanner
            label="Tỷ lệ lỗi hệ thống"
            value={errorVal}
            target={THRESHOLDS.error_rate.target}
            drillTab="errors"
            drillLabel="Tìm hiểu lỗi"
            onDrill={() => onNavigateTab("errors")}
          />
        )}
      </div>

      {/* 6 Thẻ chỉ số đo lường chính (Agent Evaluation KPIs) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <AgentEvaluationCard
          title="Tỷ lệ hoàn thành tác vụ"
          subtitle="Agent có đạt được mục tiêu yêu cầu không?"
          metric={data.task_completion ?? data.success_rate}
          percent
          thresholdKey="success_rate"
        />
        <AgentEvaluationCard
          title="Độ chính xác công cụ"
          subtitle="Đúng công cụ, đúng tham số, đúng thứ tự?"
          metric={data.tool_correctness}
          percent
          colorScheme="emerald"
        />
        <AgentEvaluationCard
          title="Độ chuẩn xác ngữ cảnh"
          subtitle="Đoạn văn bản truy xuất liên quan có xếp thứ hạng cao không?"
          metric={data.contextual_precision}
          percent
          colorScheme="rose"
        />
        <AgentEvaluationCard
          title="Độ trung thực"
          subtitle="Câu trả lời có bám sát ngữ cảnh đã truy xuất không?"
          metric={data.faithfulness}
          percent
          colorScheme="emerald"
        />
        <AgentEvaluationCard
          title="Độ trễ / tác vụ"
          subtitle="Toàn bộ quy trình từ đầu đến cuối, gồm mọi lượt gọi công cụ"
          valueOverride={latencyDisplay}
          colorScheme="sky"
        />
        <AgentEvaluationCard
          title="Chi phí / tác vụ"
          subtitle="Tổng token × đơn giá trong suốt phiên xử lý"
          valueOverride={costDisplay}
          colorScheme="amber"
        />
      </div>

      {/* Charts row: Time Series (Task Completion & Faithfulness) + Judge Score Distribution Donut */}
      <div className="grid gap-5 lg:grid-cols-2">
        {/* Time Series Trend Chart */}
        <div className="surface-card p-5 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <h3 className="text-sm font-bold flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-emerald-600" />
                Xu hướng theo thời gian (Time Series)
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Task Completion (Tỷ lệ hoàn thành) & Faithfulness (Độ trung thực)
              </p>
            </div>
            <div className="flex items-center gap-1 rounded-lg border bg-background p-1 text-xs">
              {[7, 14, 30].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setTrendDays(d)}
                  className={`rounded px-2.5 py-1 font-medium transition-colors ${
                    trendDays === d ? "bg-primary text-primary-foreground font-semibold" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {d} ngày
                </button>
              ))}
            </div>
          </div>
          {trend ? (
            <TrendChart data={trend} />
          ) : (
            <div className="h-64 flex items-center justify-center text-xs text-muted-foreground">
              Đang tải dữ liệu chuỗi thời gian...
            </div>
          )}
        </div>

        {/* Judge Score Distribution Donut Chart */}
        <div className="surface-card p-5 space-y-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold flex items-center gap-2">
                <ListChecks className="h-4 w-4 text-primary" />
                Phân bố thang điểm của Judge (0.0 – 1.0)
              </h3>
              <button
                type="button"
                onClick={() => onNavigateTab("quality")}
                className="text-xs text-primary hover:underline font-medium"
              >
                Chi tiết đánh giá →
              </button>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Phổ điểm đánh giá tự động từ mô hình LLM Judge theo 5 dải điểm chuẩn
            </p>
          </div>

          <div className="py-2">
            <DonutChart data={judgeScoreDist} title="" />
          </div>

          {safety && (
            <div className="border-t pt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <ShieldAlert className="h-3.5 w-3.5 text-rose-500" />
                Cảnh báo an toàn: <strong className="text-foreground">{safety.safety_trigger_count ?? 0}</strong>
              </span>
              <span>
                Chuyển bác sĩ: <strong className="text-foreground">{safety.handoff_required_count ?? 0}</strong>
              </span>
              <button
                type="button"
                onClick={() => onNavigateTab("safety")}
                className="text-primary hover:underline font-medium"
              >
                Xem An toàn →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Execution Path Metadata ───────────────────────────────────────────────────

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

// ─── Section: Judge ───────────────────────────────────────────────────────────

function JudgeSection({ data }: { data: JudgeOut | null }) {
  if (!data) return <LoadingState />;
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const distData = data.overall_score_distribution
    ? Object.entries(data.overall_score_distribution).map(([name, value], idx) => ({
      name,
      value,
      color: CHART_COLORS[idx % CHART_COLORS.length],
    }))
    : [];

  return (
    <div className="space-y-6 pt-4 border-t">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold flex items-center gap-2">
          <ListChecks className="h-5 w-5 text-primary" />
          Đánh giá tự động chất lượng bằng mô hình AI (LLM Judge)
        </h3>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Tổng lượt đưa vào chấm điểm" metric={{ value: data.total_judged ?? null, status: "AVAILABLE" }} integer />
        <MetricCard label="Đang chờ chấm" metric={{ value: data.judged_pending ?? null, status: "AVAILABLE" }} integer />
        <MetricCard label="Đã chấm xong" metric={{ value: data.judged_completed ?? null, status: "AVAILABLE" }} integer />
        <MetricCard label="Chấm điểm thất bại" metric={{ value: data.judged_failed ?? null, status: "AVAILABLE" }} integer />
        <MetricCard label="Chi phí mô hình Judge (USD)" metric={data.judge_cost_usd} currency />
        <MetricCard label="Token đầu vào Judge" metric={{ value: data.judge_input_tokens ?? null, status: "AVAILABLE" }} integer />
        <MetricCard label="Token đầu ra Judge" metric={{ value: data.judge_output_tokens ?? null, status: "AVAILABLE" }} integer />
      </div>

      {distData.length > 0 && (
        <div className="surface-card p-5">
          <DonutChart data={distData} title="Phân bổ thang điểm của Judge (0.0 - 1.0)" />
        </div>
      )}

      {data.disclaimer && <p className="text-xs italic text-muted-foreground">{data.disclaimer}</p>}

      {data.low_score_cases && data.low_score_cases.length > 0 && (
        <div className="surface-card overflow-x-auto p-4">
          <p className="mb-2 text-sm font-semibold">Các lượt xử lý đạt điểm thấp (&lt; 0.5)</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th>Mã Trace (Trace ID)</th>
                <th>Đường dẫn xử lý (Execution Path) & Ý nghĩa</th>
                <th>Điểm số</th>
              </tr>
            </thead>
            <tbody>
              {data.low_score_cases.map((c) => {
                const pathKey = c.execution_path ?? "";
                const meta = EXECUTION_PATH_METADATA[pathKey];
                return (
                  <tr key={c.judge_id} className="border-t hover:bg-accent/40">
                    <td className="py-2.5">
                      <Link className="text-primary underline font-mono text-xs font-semibold" href={`/admin/monitoring/traces/${c.trace_id}`}>
                        {c.trace_id?.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="py-2.5">
                      <div className="flex flex-col" title={meta?.description}>
                        <div className="font-medium text-foreground">{meta?.label ?? pathKey}</div>
                        {pathKey && <div className="font-mono text-xs text-muted-foreground">{pathKey}</div>}
                        {meta?.description && (
                          <div className="text-xs text-muted-foreground leading-relaxed max-w-lg mt-0.5">
                            {meta.description}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="font-semibold text-rose-600 py-2.5">{c.score.toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Tab: Quality ─────────────────────────────────────────────────────────────

function QualityTab({
  data,
  trend,
  trendDays,
  setTrendDays,
  judgeData,
  onNavigateTab,
}: {
  data: QualityOut;
  trend: TrendOut | null;
  trendDays: number;
  setTrendDays: (d: number) => void;
  judgeData: JudgeOut | null;
  onNavigateTab: (tab: TabId) => void;
}) {
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const faithVal =
    data.rag_faithfulness?.status === "AVAILABLE" && typeof data.rag_faithfulness.value === "number"
      ? data.rag_faithfulness.value : null;
  const relVal =
    data.rag_answer_relevance?.status === "AVAILABLE" && typeof data.rag_answer_relevance.value === "number"
      ? data.rag_answer_relevance.value : null;

  return (
    <div className="space-y-6">
      {/* Warnings */}
      <div className="space-y-2">
        {faithVal !== null && faithVal < THRESHOLDS.faithfulness.warn && (
          <WarningBanner
            label="Độ trung thực câu trả lời (Faithfulness)"
            value={faithVal}
            target={THRESHOLDS.faithfulness.target}
            drillLabel="Xem Trace Explorer"
            href="/admin/monitoring/traces"
          />
        )}
        {relVal !== null && relVal < THRESHOLDS.answer_relevance.warn && (
          <WarningBanner
            label="Độ phù hợp câu trả lời (Answer Relevance)"
            value={relVal}
            target={THRESHOLDS.answer_relevance.target}
            drillLabel="Xem Trace Explorer"
            href="/admin/monitoring/traces"
          />
        )}
      </div>

      {/* KPI cards: 3 primary cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
        <MetricCard
          label="Độ trung thực (Faithfulness)"
          metric={data.rag_faithfulness}
          thresholdKey="faithfulness"
          help="Tính trên trace trong bộ nhớ đệm hiện tại (Ring Buffer)"
        />
        <MetricCard
          label="Độ phù hợp (Answer Relevance)"
          metric={data.rag_answer_relevance}
          thresholdKey="answer_relevance"
          help="Tính trên trace trong bộ nhớ đệm hiện tại (Ring Buffer)"
        />
        <MetricCard
          label="Điểm đánh giá tổng thể (Judge Score)"
          metric={data.judge_overall_score}
          help="Tín hiệu đánh giá chất lượng tự động bằng LLM. Không phải xác nhận chuyên môn y khoa tuyệt đối."
        />
      </div>

      {/* Trend chart */}
      <div className="surface-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            Xu hướng chất lượng phản hồi ({trendDays} ngày gần nhất)
          </h3>
          <div className="flex gap-1">
            {[7, 14, 30].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setTrendDays(d)}
                className={`rounded px-2.5 py-1 text-xs font-medium ${trendDays === d ? "bg-primary text-primary-foreground" : "border hover:bg-accent"}`}
              >
                {d} ngày
              </button>
            ))}
          </div>
        </div>
        {trend ? <TrendChart data={trend} /> : <LoadingState />}
      </div>

      {/* Judge Section */}
      <JudgeSection data={judgeData} />
    </div>
  );
}

// ─── Tab: Retrieval ───────────────────────────────────────────────────────────

function RetrievalTab({
  data,
  onNavigateTab,
}: {
  data: RetrievalOut;
  onNavigateTab: (tab: TabId) => void;
}) {
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const gfVal = data.grounding_failure_rate?.status === "AVAILABLE" && typeof data.grounding_failure_rate.value === "number"
    ? data.grounding_failure_rate.value : null;

  const totalRag = data.rag_query_volume ?? 0;
  const gfCount = data.grounding_failure_rate?.numerator ?? 0;
  const ragSuccess = Math.max(0, totalRag - gfCount);

  const donutData = [
    { name: "RAG có căn cứ thành công", value: ragSuccess, color: "#10b981" },
    { name: "Lỗi thiếu căn cứ (Grounding Failure)", value: gfCount, color: "#ef4444" },
  ];

  return (
    <div className="space-y-6">
      {gfVal !== null && gfVal > THRESHOLDS.grounding_failure_rate.warn && (
        <WarningBanner
          label="Tỷ lệ lỗi thiếu căn cứ"
          value={gfVal}
          target={THRESHOLDS.grounding_failure_rate.target}
          drillTab="errors"
          drillLabel="Xem phân tích lỗi chi tiết"
          onDrill={() => onNavigateTab("errors")}
        />
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
        <MetricCard
          label="Số lượt truy vấn RAG"
          metric={{ value: data.rag_query_volume ?? null, status: "AVAILABLE" }}
          integer
        />
        <MetricCard
          label="Độ trễ truy xuất P50"
          metric={data.retrieval_latency_p50_ms}
          suffix=" ms"
          integer
        />
        <MetricCard
          label="Độ trễ truy xuất P95"
          metric={data.retrieval_latency_p95_ms}
          suffix=" ms"
          integer
        />
        <MetricCard
          label="Tỷ lệ lỗi thiếu căn cứ"
          metric={data.grounding_failure_rate}
          percent
          thresholdKey="grounding_failure_rate"
          help="Tỷ lệ yêu cầu cần căn cứ tài liệu y khoa nhưng không tìm thấy thông tin phù hợp."
        />
      </div>

      <div className="surface-card p-5">
        <DonutChart data={donutData} title="Phân bổ kết quả truy xuất RAG (Thành công vs Thiếu căn cứ)" />
      </div>
    </div>
  );
}

// ─── Tab: Performance ─────────────────────────────────────────────────────────

function PerformanceTab({ data }: { data: PerformanceOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const p95Val = data.end_to_end_p95_ms?.status === "AVAILABLE" && typeof data.end_to_end_p95_ms.value === "number"
    ? data.end_to_end_p95_ms.value : null;

  const stepBarData = data.per_step
    ? Object.entries(data.per_step)
      .map(([step, v]) => ({
        label: step,
        value: typeof v[95]?.value === "number" ? v[95].value : 0,
      }))
      .filter((d) => d.value > 0)
      .sort((a, b) => b.value - a.value)
    : [];

  return (
    <div className="space-y-6">
      {p95Val !== null && p95Val > THRESHOLDS.p95_latency_ms.warn && (
        <WarningBanner
          label="Độ trễ toàn trình P95 (End-to-End)"
          value={p95Val / 1000}
          target={THRESHOLDS.p95_latency_ms.target / 1000}
          unit="s"
          drillLabel="Xem độ trễ chi tiết từng giai đoạn"
          onDrill={() => {
            const el = document.getElementById("step-latency-table");
            el?.scrollIntoView({ behavior: "smooth" });
          }}
        />
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Độ trễ toàn trình P50 (End-to-End)" metric={data.end_to_end_p50_ms} suffix="ms" />
        <MetricCard label="Độ trễ toàn trình P95 (End-to-End)" metric={data.end_to_end_p95_ms} suffix="ms" />
        <MetricCard label="Độ trễ toàn trình P99 (End-to-End)" metric={data.end_to_end_p99_ms} suffix="ms" />
        <MetricCard label="Tỷ lệ quá thời gian (Timeout)" metric={data.timeout_rate} percent />
      </div>

      {stepBarData.length > 0 && (
        <HorizontalBarChart
          data={stepBarData}
          title="Độ trễ P95 theo từng giai đoạn xử lý (ms)"
          valueFormatter={(v) => `${v}ms`}
        />
      )}

      {data.per_step && (
        <div id="step-latency-table" className="surface-card overflow-x-auto p-4">
          <p className="mb-2 text-sm font-semibold">Bảng phân rã độ trễ chi tiết theo từng span</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="py-1">Giai đoạn (Span)</th><th>P50 (ms)</th><th>P95 (ms)</th><th>Số mẫu (n)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.per_step).map(([step, v]) => (
                <tr key={step} className="border-t">
                  <td className="py-1 font-mono text-xs">{step}</td>
                  <td>{formatMetric(v[50], { suffix: "ms" })}</td>
                  <td>{formatMetric(v[95], { suffix: "ms" })}</td>
                  <td className="text-muted-foreground">{v[50]?.sample_count ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Tab: Cost ────────────────────────────────────────────────────────────────

function CostTab({ data }: { data: CostOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const models = data.models ?? (data.by_model_usd ? Object.keys(data.by_model_usd) : []);
  const timeline = data.timeline ?? [];

  return (
    <div className="space-y-6">
      {/* 4 Cost summary KPI cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Chi phí Agent (USD)" metric={data.agent_cost_usd} currency />
        <MetricCard label="Chi phí Judge (USD)" metric={data.judge_cost_usd} currency />
        <MetricCard label="Tổng chi phí (USD)" metric={data.total_cost_usd} currency />
        <MetricCard label="Chi phí / lượt yêu cầu" metric={data.cost_per_query_usd} currency />
      </div>

      {/* 4 Token KPI cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Token đầu vào" metric={{ value: data.input_tokens ?? null, status: "AVAILABLE" }} integer />
        <MetricCard label="Token đầu ra" metric={{ value: data.output_tokens ?? null, status: "AVAILABLE" }} integer />
        <MetricCard label="Tổng Token tiêu thụ" metric={{ value: data.total_tokens ?? null, status: "AVAILABLE" }} integer />
        <MetricCard label="Token / lượt yêu cầu" metric={data.tokens_per_query} />
      </div>

      <CostTimelineChart
        timeline={timeline}
        models={models}
        title="Phân bổ chi phí theo Model AI (USD)"
      />
    </div>
  );
}

// ─── Tab: Errors ──────────────────────────────────────────────────────────────

const KNOWN_ERROR_CODES_ORDER = [
  "BUDGET_EXCEEDED", "MODEL_ERROR", "MODEL_TIMEOUT", "TOOL_ERROR", "TOOL_TIMEOUT",
  "RETRIEVAL_ERROR", "RETRIEVAL_TIMEOUT", "REQUEST_TIMEOUT", "GROUNDING_FAILURE",
  "EMPTY_REPLY", "HANDOFF_FAILURE", "INTERNAL_ERROR",
];

function ErrorsTab({ data, onDrill }: { data: ErrorsOut; onDrill: (code: string) => void }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const pieData = KNOWN_ERROR_CODES_ORDER
    .map((code, idx) => ({
      name: ERROR_CODE_METADATA[code]?.label ?? code,
      value: data.breakdown?.[code]?.numerator ?? 0,
      color: CHART_COLORS[idx % CHART_COLORS.length],
    }))
    .filter((d) => d.value > 0);

  return (
    <div className="space-y-6">
      {pieData.length > 0 && (
        <div className="surface-card p-5">
          <DonutChart data={pieData} title="Phân bổ nguyên nhân phát sinh lỗi" />
        </div>
      )}
      <div className="surface-card overflow-x-auto p-4">
        <p className="mb-2 text-sm text-muted-foreground">
          Tổng số lượt yêu cầu: {data.total_requests ?? "N/A"}. (Nhấp vào một mã lỗi để lọc danh sách trace tương ứng)
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-2">Nguyên nhân & Mã lỗi</th>
              <th>Tỷ lệ phát sinh</th>
              <th>Số lượng ca</th>
              <th>Ghi chú kỹ thuật & Ý nghĩa</th>
            </tr>
          </thead>
          <tbody>
            {KNOWN_ERROR_CODES_ORDER.map((code) => {
              const m = data.breakdown?.[code];
              const count = m?.numerator ?? 0;
              const meta = ERROR_CODE_METADATA[code];
              const backendNote = formatHumanNote(m?.note);
              return (
                <tr
                  key={code}
                  className={`cursor-pointer border-t hover:bg-accent/50 ${count > 0 ? "" : "opacity-60"}`}
                  onClick={() => onDrill(code)}
                >
                  <td className="py-2.5">
                    <div className="font-medium text-foreground">{meta?.label ?? code}</div>
                    <div className="font-mono text-xs text-muted-foreground">{code}</div>
                  </td>
                  <td>{formatMetric(m, { percent: true })}</td>
                  <td className={count > 0 ? "font-semibold text-rose-600" : ""}>{m?.numerator ?? "N/A"}</td>
                  <td className="text-xs text-muted-foreground leading-relaxed max-w-md">
                    <div>{meta?.description ?? ""}</div>
                    {backendNote && (
                      <div className="mt-0.5 text-[11px] italic text-amber-700 dark:text-amber-400">
                        {backendNote}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {data.unrecognized_error_codes && data.unrecognized_error_codes.length > 0 && (
          <p className="mt-2 text-xs text-amber-600">
            Mã lỗi chưa nằm trong danh mục chuẩn: {data.unrecognized_error_codes.join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}



// ─── Tab: Golden ──────────────────────────────────────────────────────────────

function GoldenTab({ data }: { data: GoldenOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;
  if (!data.has_run || !data.latest_run) {
    return (
      <div className="surface-card p-4 text-sm text-muted-foreground">
        Chưa có lượt đánh giá chuẩn nào được lưu. Chạy{" "}
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
          run_golden_evaluation.py --persist
        </code>{" "}
        để cập nhật dữ liệu.
      </div>
    );
  }
  const run = data.latest_run;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Phiên bản bộ dữ liệu chuẩn" metric={{ value: run.golden_set_version, status: "AVAILABLE" }} />
        <MetricCard
          label="Tỷ lệ ca đạt chuẩn (Pass Rate)"
          metric={{ value: run.pass_rate, status: run.pass_rate !== null ? "AVAILABLE" : "NOT_APPLICABLE" }}
          percent
        />
        <MetricCard
          label="Cổng kiểm thử hồi quy (Regression Gate)"
          metric={{ value: run.regression_gate_passed ? "ĐẠT (PASS)" : "KHÔNG ĐẠT (FAIL)", status: "AVAILABLE" }}
        />
        <MetricCard
          label="Số ca kiểm thử (Đạt / Tổng)"
          metric={{ value: `${run.passed_cases}/${run.total_cases}`, status: "AVAILABLE" }}
        />
      </div>
      <div className="surface-card p-4">
        <p className="mb-2 text-sm font-semibold">Kết quả kiểm thử theo phân loại (Category)</p>
        <table className="w-full text-sm">
          <tbody>
            {Object.entries(run.by_category).map(([cat, v]) => (
              <tr key={cat} className="border-t">
                <td className="py-1 font-medium">{cat}</td>
                <td className="font-semibold">{v.passed}/{v.total}</td>
                <td>
                  <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-emerald-500"
                      style={{ width: `${v.total > 0 ? (v.passed / v.total) * 100 : 0}%` }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {run.failed_case_ids.length > 0 && (
        <div className="surface-card p-4">
          <p className="mb-1 text-sm font-semibold text-destructive">
            Các ca kiểm thử không đạt: {run.failed_case_ids.join(", ")}
          </p>
        </div>
      )}
      <p className="text-xs italic text-muted-foreground">
        Lưu ý: Phân loại FALLBACK chưa có ca kiểm thử toàn trình thực tế.
      </p>
    </div>
  );
}

// ─── Tab: Versions ────────────────────────────────────────────────────────────

function VersionsTab({
  accessToken,
  versionOptions,
}: {
  accessToken: string | null | undefined;
  versionOptions?: VersionFiltersOut | null;
}) {
  const [section, setSection] = useState("overview");
  const [before, setBefore] = useState<MonitoringFiltersInput>({});
  const [after, setAfter] = useState<MonitoringFiltersInput>({});
  const [result, setResult] = useState<CompareOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const SECTION_LABELS: Record<string, string> = {
    overview: "Tổng quan (Overview)",
    quality: "Chất lượng (Quality)",
    retrieval: "Truy xuất (Retrieval)",
    performance: "Hiệu năng (Performance)",
    cost: "Chi phí (Cost)",
    errors: "Phân tích lỗi (Errors)",
    judge: "Đánh giá (Judge)",
  };

  const INPUT_LABELS: Record<string, string> = {
    "Before model": "Model ban đầu (Before)",
    "Before prompt_version": "Prompt Version ban đầu",
    "After model": "Model sau (After)",
    "After prompt_version": "Prompt Version sau",
  };

  const availableModels = versionOptions?.model ?? [];
  const availablePromptVersions = versionOptions?.prompt_version ?? [];

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await compareVersions(section, before, after, accessToken));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi không xác định");
    } finally {
      setLoading(false);
    }
  }, [section, before, after, accessToken]);

  return (
    <div className="space-y-4">
      <div className="surface-card flex flex-wrap items-end gap-3 p-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Hạng mục so sánh</label>
          <select
            className="rounded border bg-background px-2 py-1 text-sm h-8"
            value={section}
            onChange={(e) => setSection(e.target.value)}
          >
            {Object.entries(SECTION_LABELS).map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </div>
        {(["Before model", "Before prompt_version", "After model", "After prompt_version"] as const).map((lbl) => {
          const isBefore = lbl.startsWith("Before");
          const isModel = lbl.includes("model");
          const field = isModel ? "model" : "promptVersion";
          const rawOptions = isModel ? availableModels : availablePromptVersions;
          const cur = isBefore ? before : after;
          const set = isBefore ? setBefore : setAfter;
          const currentValue = (cur as Record<string, string | undefined>)[field] ?? "";
          const optionsList = Array.from(new Set(currentValue ? [currentValue, ...rawOptions] : rawOptions));

          return (
            <div key={lbl} className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">{INPUT_LABELS[lbl] ?? lbl}</label>
              <select
                className="rounded border bg-background px-2.5 py-1 text-sm h-8 min-w-[160px]"
                value={currentValue}
                onChange={(e) => set({ ...cur, [field]: e.target.value || undefined })}
              >
                <option value="">{isModel ? "Chọn model..." : "Chọn prompt version..."}</option>
                {optionsList.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
        <button
          type="button"
          className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground font-medium h-8 flex items-center"
          onClick={run}
        >
          Bắt đầu so sánh
        </button>
      </div>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} />}
      {result && result.available && (
        <pre className="surface-card overflow-x-auto p-4 text-xs">
          {JSON.stringify(result.comparison, null, 2)}
        </pre>
      )}
      {result && !result.available && <UnavailableState reason={result.reason} />}
    </div>
  );
}

// ─── Tab: RAG Chatbot (embedded from /admin/rag) ──────────────────────────────

type RagActiveTab = "overview" | "retrieval" | "generation" | "safety" | "system" | "traces";
type NumericMetric = number | null;

interface RagMetricBag {
  [key: string]: NumericMetric | undefined;
  faithfulness?: NumericMetric;
  answer_relevance?: NumericMetric;
  hallucination_rate?: NumericMetric;
  abstention_accuracy?: NumericMetric;
  hit_rate_10?: NumericMetric;
  mrr_10?: NumericMetric;
  ndcg_10?: NumericMetric;
  total_indexed_chunks?: number;
  evaluated_sample_count?: number;
  p95_latency_ms?: number;
  critical_safety_failure_rate?: number;
}
interface RagHealthData {
  status: string;
  kpis: RagMetricBag;
  trend: { date: string; faithfulness: NumericMetric; relevance: NumericMetric; latency_p95: number; requests: number }[];
}
interface RagWorstQuery {
  query: string; count: number; avg_top1: number; precision: number; recall: number; faithfulness: number; last_seen: string;
}
interface RagRetrievalData { metrics: RagMetricBag; worst_queries: RagWorstQuery[] }
interface RagGenerationModelBreakdown { model: string; requests: number; faithfulness: NumericMetric }
interface RagGenerationData { metrics: RagMetricBag; breakdown_by_model: RagGenerationModelBreakdown[] }
interface RagSafetyData {
  critical_safety_failures?: number;
  dosage_consistency_failures?: number;
  interaction_unsupported_claims?: number;
  incidents: { id: string; severity: string; reason?: string; failure_type?: string; status: string }[];
}
interface RagSystemData {
  latency_waterfall: { component: string; duration_ms: number }[];
}
interface RagTrace {
  trace_id: string; timestamp: string; query_preview: string; final_answer: string; latency_ms: number;
  faithfulness: NumericMetric; relevance: NumericMetric; status: string; model: string;
}

function RagChatbotTab({ accessToken }: { accessToken: string | null | undefined }) {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const [ragTab, setRagTab] = useState<RagActiveTab>("overview");
  const [healthData, setHealthData] = useState<RagHealthData | null>(null);
  const [retrievalData, setRetrievalData] = useState<RagRetrievalData | null>(null);
  const [generationData, setGenerationData] = useState<RagGenerationData | null>(null);
  const [safetyData, setSafetyData] = useState<RagSafetyData | null>(null);
  const [systemData, setSystemData] = useState<RagSystemData | null>(null);
  const [traces, setTraces] = useState<RagTrace[]>([]);
  const [loading, setLoading] = useState(true);
  const [chatbotFilter, setChatbotFilter] = useState("agent-v2");
  const [modelFilter, setModelFilter] = useState("all");
  const [filterOptions, setFilterOptions] = useState<{
    chatbot_versions: { value: string; label: string }[];
    models: string[];
    prompt_versions: string[];
    environments: string[];
  }>({ chatbot_versions: [], models: [], prompt_versions: [], environments: [] });

  const fetchRagData = useCallback(async (bg = false) => {
    if (!accessToken) return;
    if (!bg) setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${accessToken}` };
      const qs = new URLSearchParams();
      if (chatbotFilter !== "all") qs.set("chatbot_version", chatbotFilter);
      if (modelFilter !== "all") qs.set("model", modelFilter);
      const q = qs.toString() ? `?${qs.toString()}` : "";

      const readJson = async <T,>(r: Response): Promise<T | null> => r.ok ? r.json() : null;
      const [h, ret, gen, saf, sys, tr, fil] = await Promise.all([
        fetch(`${apiBase}/api/v1/admin/rag/health${q}`, { headers }).then(readJson<RagHealthData>).catch(() => null),
        fetch(`${apiBase}/api/v1/admin/rag/retrieval${q}`, { headers }).then(readJson<RagRetrievalData>).catch(() => null),
        fetch(`${apiBase}/api/v1/admin/rag/generation${q}`, { headers }).then(readJson<RagGenerationData>).catch(() => null),
        fetch(`${apiBase}/api/v1/admin/rag/safety${q}`, { headers }).then(readJson<RagSafetyData>).catch(() => null),
        fetch(`${apiBase}/api/v1/admin/rag/system${q}`, { headers }).then(readJson<RagSystemData>).catch(() => null),
        fetch(`${apiBase}/api/v1/admin/rag/traces${q}`, { headers }).then(async (r) => (await readJson<RagTrace[]>(r)) ?? []).catch(() => [] as RagTrace[]),
        fetch(`${apiBase}/api/v1/admin/rag/filters`, { headers }).then(readJson<typeof filterOptions>).catch(() => null),
      ]);
      if (h) setHealthData(h);
      if (ret) setRetrievalData(ret);
      if (gen) setGenerationData(gen);
      if (saf) setSafetyData(saf);
      if (sys) setSystemData(sys);
      if (Array.isArray(tr)) setTraces(tr);
      if (fil) setFilterOptions(fil);
    } finally {
      if (!bg) setLoading(false);
    }
  }, [accessToken, apiBase, chatbotFilter, modelFilter]);

  useEffect(() => {
    fetchRagData();
    const id = setInterval(() => fetchRagData(true), 10000);
    return () => clearInterval(id);
  }, [fetchRagData]);

  const kpis = healthData?.kpis ?? {};
  const safePct = (v: NumericMetric | undefined) => {
    const n = Number(v);
    return isNaN(n) ? 0 : n <= 1.0 ? Math.round(n * 100) : Math.round(n);
  };
  const metricPct = (v: NumericMetric | undefined) => typeof v === "number" ? `${safePct(v)}%` : "N/A";

  const RAG_TABS: { id: RagActiveTab; label: string }[] = [
    { id: "overview", label: "Tổng quan & Sức khỏe hệ thống" },
    { id: "retrieval", label: "Chất lượng truy xuất (Retrieval)" },
    { id: "generation", label: "Chất lượng sinh phản hồi (Generation)" },
    { id: "safety", label: "An toàn & Sự cố thuốc" },
    { id: "system", label: "Độ trễ & Pipeline" },
    { id: "traces", label: "Nhật ký Trace thực tế" },
  ];

  return (
    <div className="space-y-6">
      {/* RAG header */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="rounded-full bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-700">
          Langfuse Observability
        </span>
        <span className="flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
          Giám sát trực tiếp (10s)
        </span>
        <button
          type="button"
          onClick={() => fetchRagData(false)}
          className="ml-auto flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs hover:bg-accent"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Làm mới
        </button>
      </div>

      {/* RAG filter bar */}
      <div className="surface-card flex flex-wrap items-center gap-3 p-3 text-sm">
        <Filter className="h-3.5 w-3.5 text-primary" />
        <select
          value={chatbotFilter}
          onChange={(e) => setChatbotFilter(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2.5 text-xs font-medium"
        >
          <option value="all">Phiên bản Chatbot: Tất cả</option>
          {filterOptions.chatbot_versions.map((v) => (
            <option key={v.value} value={v.value}>Phiên bản: {v.label}</option>
          ))}
        </select>
        <select
          value={modelFilter}
          onChange={(e) => setModelFilter(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2.5 text-xs font-medium"
        >
          <option value="all">Model AI: Tất cả</option>
          {filterOptions.models.map((m) => <option key={m} value={m}>Model: {m}</option>)}
        </select>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          <span className="text-muted-foreground">Trạng thái RAG:</span>
          <span className="font-semibold text-emerald-600">{healthData?.status || "Live"}</span>
        </div>
      </div>

      {/* RAG sub-tabs */}
      <div className="flex border-b border-border gap-1 overflow-x-auto text-sm font-medium">
        {RAG_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setRagTab(t.id)}
            className={`whitespace-nowrap px-4 py-2.5 border-b-2 transition ${ragTab === t.id ? "border-primary text-primary font-semibold" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && <LoadingState />}

      {/* RAG sub-tab content */}
      {!loading && ragTab === "overview" && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Độ trung thực (Faithfulness)", value: metricPct(kpis.faithfulness), target: "Mục tiêu ≥ 85%", color: "emerald" },
              { label: "Độ phù hợp (Answer Relevance)", value: metricPct(kpis.answer_relevance), target: "Mục tiêu ≥ 80%", color: "blue" },
              { label: "Độ trễ toàn trình P95", value: `${kpis.p95_latency_ms || 0}ms`, target: "End-to-End", color: "slate" },
              { label: "Sự cố an toàn y tế", value: `${safetyData?.critical_safety_failures ?? 0} sự cố`, target: "Ngưỡng chặn nghiêm ngặt", color: "emerald" },
            ].map((card) => (
              <div key={card.label} className="surface-card p-5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground uppercase">{card.label}</span>
                  <span className={`rounded-full bg-${card.color}-50 text-${card.color}-700 border border-${card.color}-200 px-2 py-0.5 text-[11px] font-semibold`}>
                    {card.target}
                  </span>
                </div>
                <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">{card.value}</p>
              </div>
            ))}
          </div>

          {healthData && healthData.trend.length > 0 && !healthData.trend.every((t) => t.requests === 0) && (
            <div className="surface-card p-5">
              <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary" />
                Xu hướng chất lượng RAG (7 ngày gần nhất)
              </h3>
              <div className="h-60 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={healthData.trend}>
                    <defs>
                      <linearGradient id="rFaith" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="date" fontSize={11} stroke="var(--muted-foreground)" />
                    <YAxis domain={[0, 1]} fontSize={11} stroke="var(--muted-foreground)" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                    <Tooltip contentStyle={{ borderRadius: "8px", fontSize: "12px" }} />
                    <Area type="monotone" dataKey="faithfulness" name="Faithfulness" stroke="#10b981" strokeWidth={2} fill="url(#rFaith)" />
                    <Area type="monotone" dataKey="relevance" name="Relevance" stroke="#2563eb" strokeWidth={2} fill="url(#gRel)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && ragTab === "retrieval" && (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-4">
            {[
              { label: "Tỷ lệ tìm thấy Top 10 (HitRate@10)", val: retrievalData?.metrics?.hit_rate_10, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
              { label: "Thứ hạng đảo trung bình (MRR@10)", val: retrievalData?.metrics?.mrr_10, fmt: (v: number) => v.toFixed(2) },
              { label: "Độ chuẩn tích lũy chiết khấu (NDCG@10)", val: retrievalData?.metrics?.ndcg_10, fmt: (v: number) => v.toFixed(2) },
              { label: "Tổng số đoạn tài liệu (Chunks)", val: retrievalData?.metrics?.total_indexed_chunks, fmt: (v: number) => String(v) },
            ].map(({ label, val, fmt }) => (
              <div key={label} className="surface-card p-5">
                <span className="text-xs font-semibold text-muted-foreground uppercase">{label}</span>
                <p className="mt-2 text-3xl font-extrabold text-primary">
                  {typeof val === "number" ? fmt(val) : "N/A"}
                </p>
                {typeof val !== "number" && (
                  <p className="mt-1 text-[10px] text-muted-foreground italic">Cần đủ dữ liệu trace để tính</p>
                )}
              </div>
            ))}
          </div>
          {(retrievalData?.worst_queries ?? []).length > 0 && (
            <div className="surface-card p-5">
              <h3 className="font-bold flex items-center gap-2 mb-3">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                Truy vấn đạt kết quả thấp nhất (Worst Queries)
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-sm text-left">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="py-2 px-3">Câu truy vấn</th>
                      <th className="py-2 px-3">Lượt</th>
                      <th className="py-2 px-3">Top-1</th>
                      <th className="py-2 px-3">Độ chính xác (Precision)</th>
                      <th className="py-2 px-3">Độ bao phủ (Recall)</th>
                      <th className="py-2 px-3">Độ trung thực (Faithfulness)</th>
                      <th className="py-2 px-3">Lần cuối</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {retrievalData!.worst_queries.map((q, i) => (
                      <tr key={i} className="hover:bg-muted/30">
                        <td className="py-2 px-3 font-medium max-w-xs truncate">{q.query}</td>
                        <td className="py-2 px-3">{q.count}</td>
                        <td className="py-2 px-3 font-semibold text-amber-600">{q.avg_top1}</td>
                        <td className="py-2 px-3">{q.precision}</td>
                        <td className="py-2 px-3">{q.recall}</td>
                        <td className="py-2 px-3 font-semibold text-primary">{q.faithfulness}</td>
                        <td className="py-2 px-3 text-xs text-muted-foreground">{q.last_seen}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {!loading && ragTab === "generation" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="surface-card p-5 space-y-3">
            <h3 className="font-bold flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /> Chất lượng sinh phản hồi (Generation)</h3>
            {[
              { label: "Độ trung thực (Faithfulness)", val: generationData?.metrics?.faithfulness },
              { label: "Độ phù hợp câu trả lời (Answer Relevance)", val: generationData?.metrics?.answer_relevance },
              { label: "Tỷ lệ thông tin suy diễn / ảo giác (Hallucination)", val: generationData?.metrics?.hallucination_rate },
              { label: "Độ chính xác khi từ chối trả lời (Abstention)", val: generationData?.metrics?.abstention_accuracy },
            ].map(({ label, val }) => (
              <div key={label} className="flex justify-between py-2 border-b border-border last:border-0 text-sm">
                <span className="text-muted-foreground">{label}</span>
                <span className="font-bold">{metricPct(val)}</span>
              </div>
            ))}
          </div>
          <div className="surface-card p-5 space-y-3">
            <h3 className="font-bold">Phân bổ hiệu quả theo Model AI</h3>
            {(generationData?.breakdown_by_model ?? []).map((m, i) => (
              <div key={i} className="p-3 bg-muted/40 rounded-lg">
                <div className="flex justify-between font-semibold text-sm">
                  <span>{m.model}</span>
                  <span className="text-emerald-600">{m.requests} lượt</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">Faithfulness: {safePct(m.faithfulness)}%</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && ragTab === "safety" && (
        <div className="surface-card p-5 space-y-4">
          <h3 className="font-bold flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-rose-500" /> Giám sát An toàn Y tế & Liều dùng
          </h3>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              { label: "Lỗi liều lượng / tần suất", val: safetyData?.dosage_consistency_failures ?? 0 },
              { label: "Tuyên bố tương tác thuốc thiếu căn cứ", val: safetyData?.interaction_unsupported_claims ?? 0 },
              { label: "Tổng số ca chuyển tiếp bác sĩ", val: (safetyData?.incidents ?? []).length },
            ].map(({ label, val }) => (
              <div key={label} className="surface-card p-4 bg-muted/30">
                <span className="text-xs text-muted-foreground font-semibold uppercase">{label}</span>
                <p className="mt-1 text-2xl font-bold text-emerald-600">{val} ca</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && ragTab === "system" && (
        <div className="surface-card p-5 space-y-4">
          <h3 className="font-bold flex items-center gap-2"><Zap className="h-4 w-4 text-primary" /> Phân rã Độ trễ Pipeline</h3>
          {(!systemData?.latency_waterfall || systemData.latency_waterfall.length === 0) ? (
            <p className="text-sm text-muted-foreground text-center py-8">Chưa có dữ liệu span.</p>
          ) : (() => {
            const max = Math.max(...systemData.latency_waterfall.map((s) => s.duration_ms || 0), 1);
            return systemData.latency_waterfall.map((step, i) => (
              <div key={i} className="space-y-1">
                <div className="flex justify-between text-xs font-semibold">
                  <span className="font-mono">{step.component}</span>
                  <span className="text-muted-foreground">{step.duration_ms}ms</span>
                </div>
                <div className="w-full bg-muted h-2.5 rounded-full overflow-hidden">
                  <div
                    className="bg-primary h-full rounded-full transition-all duration-300"
                    style={{ width: `${Math.max(2, Math.round((step.duration_ms / max) * 100))}%` }}
                  />
                </div>
              </div>
            ));
          })()}
        </div>
      )}

      {!loading && ragTab === "traces" && (
        <div className="surface-card overflow-hidden">
          <div className="p-4 border-b flex items-center justify-between">
            <h3 className="font-bold">Nhật ký Trace thực tế</h3>
            <span className="text-xs text-muted-foreground">{traces.length} bản ghi</span>
          </div>
          {traces.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">Chưa có trace nào.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm text-left">
                <thead>
                  <tr className="border-b bg-muted/50 text-xs text-muted-foreground">
                    <th className="py-3 px-4">Trace ID</th>
                    <th className="py-3 px-4">Thời gian</th>
                    <th className="py-3 px-4">Câu hỏi</th>
                    <th className="py-3 px-4">Độ trễ</th>
                    <th className="py-3 px-4">Độ trung thực (Faithfulness)</th>
                    <th className="py-3 px-4">Độ phù hợp (Relevance)</th>
                    <th className="py-3 px-4">Trạng thái</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {traces.map((t, i) => (
                    <tr key={i} className="hover:bg-muted/30">
                      <td className="py-3 px-4 font-mono text-xs text-primary font-semibold">{t.trace_id}</td>
                      <td className="py-3 px-4 text-xs text-muted-foreground">
                        {new Date(t.timestamp).toLocaleTimeString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                      </td>
                      <td className="py-3 px-4 max-w-xs truncate font-medium">{t.query_preview}</td>
                      <td className="py-3 px-4 text-muted-foreground">{t.latency_ms}ms</td>
                      <td className="py-3 px-4 font-semibold text-emerald-600">{t.faithfulness ?? "—"}</td>
                      <td className="py-3 px-4 font-semibold text-primary">{t.relevance ?? "—"}</td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${t.status === "success" ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-rose-50 text-rose-700 border border-rose-200"}`}>
                          {t.status === "success" ? "Thành công" : t.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Safety Metadata ─────────────────────────────────────────────────────────

const SEVERITY_METADATA: Record<string, { label: string; color: string; bgClass: string }> = {
  CRITICAL: { label: "Khẩn cấp", color: "#ef4444", bgClass: "bg-rose-500/10 text-rose-600 border-rose-500/20" },
  HIGH: { label: "Cao", color: "#f97316", bgClass: "bg-orange-500/10 text-orange-600 border-orange-500/20" },
  MEDIUM: { label: "Trung bình", color: "#f59e0b", bgClass: "bg-amber-500/10 text-amber-600 border-amber-500/20" },
  LOW: { label: "Thấp", color: "#10b981", bgClass: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" },
};

const SAFETY_REASON_METADATA: Record<string, { label: string; description: string }> = {
  ACUTE_DANGER_DETECTED: {
    label: "Phát hiện nguy hiểm cấp tính",
    description: "Phát hiện dấu hiệu cấp cứu hoặc triệu chứng nguy hiểm đe dọa tính mạng cần can thiệp y tế ngay.",
  },
  DOSE_UNRESOLVED: {
    label: "Chưa xác định được liều lượng",
    description: "Không đủ thông tin an toàn để tính toán hoặc khuyến cáo liều dùng chính xác.",
  },
  DRUG_INTERACTION: {
    label: "Tương tác thuốc nguy hiểm",
    description: "Phát hiện nguy cơ tương tác bất lợi giữa các loại thuốc trong đơn hoặc tiền sử.",
  },
  CONTRAINDICATION: {
    label: "Chống chỉ định dùng thuốc",
    description: "Thuốc bị chống chỉ định đối với tình trạng bệnh lý hoặc tiền sử dị ứng của bệnh nhân.",
  },
  SPECIAL_POPULATION: {
    label: "Đối tượng nguy cơ đặc biệt",
    description: "Bệnh nhân thuộc nhóm đặc biệt (phụ nữ mang thai, cho con bú, trẻ nhỏ, suy gan/thận).",
  },
  HIGH_RISK_SYMPTOM: {
    label: "Triệu chứng nguy cơ cao",
    description: "Triệu chứng bất thường kéo dài hoặc trở nặng cần bác sĩ chuyên khoa thăm khám trực tiếp.",
  },
  SAFETY_ANOMALY: {
    label: "Bất thường về an toàn",
    description: "Hệ thống phát hiện tín hiệu bất thường trong câu trả lời cần kiểm tra an toàn.",
  },
};

const HANDOFF_STATUS_METADATA: Record<string, { label: string; bgClass: string }> = {
  PENDING: { label: "Đang chờ xử lý", bgClass: "bg-amber-500/10 text-amber-600 border-amber-500/20" },
  ASSIGNED: { label: "Đang xử lý", bgClass: "bg-sky-500/10 text-sky-600 border-sky-500/20" },
  RESOLVED: { label: "Đã hoàn tất", bgClass: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" },
  FAILED: { label: "Thất bại", bgClass: "bg-rose-500/10 text-rose-600 border-rose-500/20" },
};

// ─── Tab: Safety ─────────────────────────────────────────────────────────────

interface SafetyEventItem {
  id: string;
  agent_run_id: string | null;
  trace_id: string | null;
  conversation_id: string | null;
  outcome: string;
  reason_code: string;
  severity: string;
  severity_source: string;
  handoff_required: boolean;
  handoff_created: boolean;
  handoff_id: string | null;
  handoff_status_live: string | null;
  handoff_resolved: boolean;
  handoff_resolved_at: string | null;
  time_to_review_seconds: number | null;
  error_code: string | null;
  created_at: string | null;
}

interface SafetySummaryFull {
  available?: boolean;
  safety_trigger_count?: number;
  safety_trigger_rate?: number | null;
  handoff_required_count?: number;
  handoff_required_rate?: number | null;
  handoff_created_count?: number;
  handoff_created_rate?: number | null;
  handoff_failure_count?: number;
  handoff_failure_rate?: number | null;
  unresolved_handoff_count?: number;
  time_to_review_avg_seconds?: number | null;
  time_to_review_sample_count?: number;
  denominator_agent_v2_total_runs?: number;
  severity_distribution?: Record<string, number>;
  reason_code_distribution?: Record<string, number>;
  handoff_status_distribution?: Record<string, number>;
  legacy_escalation_count?: number;
}

interface SafetySummary {
  safety_trigger_count?: number;
  handoff_required_count?: number;
  denominator_agent_v2_total_runs?: number;
}

function SafetyTab({
  accessToken,
  filters,
}: {
  accessToken: string | null | undefined;
  filters: MonitoringFiltersInput;
}) {
  const [summary, setSummary] = useState<SafetySummaryFull | null>(null);
  const [events, setEvents] = useState<SafetyEventItem[]>([]);
  const [totalEvents, setTotalEvents] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSafety = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const [sumData, evData] = await Promise.all([
        getSafetySummary(filters, accessToken),
        getSafetyEvents(filters, { limit: 50, accessToken }),
      ]);
      setSummary(sumData as SafetySummaryFull);
      setEvents((evData.items as SafetyEventItem[]) ?? []);
      setTotalEvents(evData.total ?? 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi tải dữ liệu an toàn");
    } finally {
      setLoading(false);
    }
  }, [accessToken, filters]);

  useEffect(() => {
    fetchSafety();
  }, [fetchSafety]);

  const severityPie = summary?.severity_distribution
    ? Object.entries(summary.severity_distribution)
      .map(([name, value]) => {
        const meta = SEVERITY_METADATA[name];
        return {
          name: meta?.label ?? name,
          value,
          color: meta?.color ?? "#10b981",
        };
      })
      .filter((d) => d.value > 0)
    : [];

  const reasonPie = summary?.reason_code_distribution
    ? Object.entries(summary.reason_code_distribution)
      .map(([name, value], idx) => {
        const meta = SAFETY_REASON_METADATA[name];
        return {
          name: meta?.label ?? formatHumanNote(name) ?? name,
          value,
          color: CHART_COLORS[idx % CHART_COLORS.length],
        };
      })
      .filter((d) => d.value > 0)
    : [];

  return (
    <div className="space-y-6">
      {loading && <LoadingState />}
      {error && <ErrorState message={error} />}

      {summary && (
        <>
          {/* KPI Grid */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <MetricCard
              label="Kích hoạt cảnh báo an toàn"
              metric={{ value: summary.safety_trigger_count ?? 0, status: "AVAILABLE" }}
              integer
              sub={summary.safety_trigger_rate !== null && summary.safety_trigger_rate !== undefined ? `Tỷ lệ: ${(summary.safety_trigger_rate * 100).toFixed(2)}%` : undefined}
            />
            <MetricCard
              label="Yêu cầu chuyển bác sĩ"
              metric={{ value: summary.handoff_required_count ?? 0, status: "AVAILABLE" }}
              integer
              sub={summary.handoff_required_rate !== null && summary.handoff_required_rate !== undefined ? `Tỷ lệ: ${(summary.handoff_required_rate * 100).toFixed(2)}%` : undefined}
            />
            <MetricCard
              label="Thời gian duyệt trung bình"
              metric={{
                value: summary.time_to_review_avg_seconds != null ? Math.round(summary.time_to_review_avg_seconds) : null,
                status: summary.time_to_review_avg_seconds != null ? "AVAILABLE" : "NOT_APPLICABLE",
              }}
              suffix="s"
              integer
              sub={summary.time_to_review_sample_count ? `${summary.time_to_review_sample_count} ca đã duyệt` : undefined}
            />
            <MetricCard
              label="Chuyển tiếp bác sĩ thất bại"
              metric={{ value: summary.handoff_failure_count ?? 0, status: "AVAILABLE" }}
              integer
            />
          </div>

          {/* Charts */}
          <div className="grid gap-4 md:grid-cols-2">
            {severityPie.length > 0 ? (
              <div className="surface-card p-5">
                <DonutChart data={severityPie} title="Phân bổ mức độ nghiêm trọng" />
              </div>
            ) : (
              <div className="surface-card p-5 flex items-center justify-center text-xs text-muted-foreground">
                Chưa có sự kiện phân loại mức độ nghiêm trọng
              </div>
            )}
            {reasonPie.length > 0 ? (
              <div className="surface-card p-5">
                <DonutChart data={reasonPie} title="Phân bổ nguyên nhân an toàn" />
              </div>
            ) : (
              <div className="surface-card p-5 flex items-center justify-center text-xs text-muted-foreground">
                Chưa có dữ liệu nguyên nhân an toàn
              </div>
            )}
          </div>

          {/* Events table */}
          <div className="surface-card overflow-x-auto p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-sm">Danh sách sự kiện an toàn & Chuyển bác sĩ</h3>
                <p className="text-xs text-muted-foreground">
                  Ghi nhận {totalEvents.toLocaleString("vi-VN")} sự kiện (hiển thị 50 sự kiện gần nhất)
                </p>
              </div>
            </div>
            {events.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">Chưa có sự kiện an toàn nào</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted-foreground border-b">
                    <th className="pb-2">Trace ID</th>
                    <th className="pb-2">Mức độ</th>
                    <th className="pb-2">Nguyên nhân & Ý nghĩa</th>
                    <th className="pb-2">Chuyển tiếp</th>
                    <th className="pb-2">Trạng thái Xử lý</th>
                    <th className="pb-2">Thời gian tạo</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {events.map((ev) => {
                    const sevMeta = SEVERITY_METADATA[ev.severity];
                    const reasonMeta = SAFETY_REASON_METADATA[ev.reason_code];
                    const statusMeta = ev.handoff_status_live ? HANDOFF_STATUS_METADATA[ev.handoff_status_live] : null;
                    return (
                      <tr key={ev.id} className="hover:bg-accent/40">
                        <td className="py-2.5 font-mono text-xs">
                          {ev.trace_id ? (
                            <Link href={`/admin/monitoring/traces/${ev.trace_id}`} className="text-primary underline">
                              {ev.trace_id.slice(0, 8)}
                            </Link>
                          ) : (
                            <span className="text-muted-foreground">N/A</span>
                          )}
                        </td>
                        <td className="py-2.5">
                          <span
                            className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold ${
                              sevMeta?.bgClass ?? "bg-muted text-muted-foreground"
                            }`}
                          >
                            {sevMeta?.label ?? ev.severity}
                          </span>
                        </td>
                        <td className="py-2.5 text-xs max-w-xs">
                          <div className="font-medium text-foreground">{reasonMeta?.label ?? formatHumanNote(ev.reason_code) ?? ev.reason_code}</div>
                          <div className="font-mono text-[10px] text-muted-foreground">{ev.reason_code}</div>
                          {reasonMeta?.description && (
                            <div className="text-[11px] text-muted-foreground/80 mt-0.5 line-clamp-1" title={reasonMeta.description}>
                              {reasonMeta.description}
                            </div>
                          )}
                        </td>
                        <td className="py-2.5 text-xs">
                          {ev.handoff_created ? (
                            <span className="inline-flex rounded bg-emerald-500/10 px-2 py-0.5 text-emerald-600 font-medium">
                              Đã tạo
                            </span>
                          ) : ev.handoff_required ? (
                            <span className="inline-flex rounded bg-rose-500/10 px-2 py-0.5 text-rose-600 font-medium">
                              Bắt buộc
                            </span>
                          ) : (
                            <span className="text-muted-foreground">Không</span>
                          )}
                        </td>
                        <td className="py-2.5 text-xs">
                          {statusMeta ? (
                            <span className={`inline-flex rounded px-2 py-0.5 font-medium ${statusMeta.bgClass}`}>
                              {statusMeta.label}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">{ev.handoff_status_live ?? "—"}</span>
                          )}
                        </td>
                        <td className="py-2.5 text-xs text-muted-foreground">
                          {ev.created_at ? new Date(ev.created_at).toLocaleString("vi-VN", {
                            timeZone: "Asia/Ho_Chi_Minh",
                            hour: "2-digit",
                            minute: "2-digit",
                            day: "2-digit",
                            month: "2-digit",
                            year: "numeric",
                          }) : "N/A"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function AdminMonitoringUnifiedDashboard() {
  const { accessToken } = useAuth();
  const searchParams = useSearchParams();
  const router = useRouter();

  const tabFromUrl = searchParams.get("tab") as TabId | null;
  const initialTab = tabFromUrl && TABS.some((t) => t.id === tabFromUrl) ? tabFromUrl : "overview";

  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [filters, setFilters] = useState<MonitoringFiltersInput>({});
  const [versionOptions, setVersionOptions] = useState<VersionFiltersOut | null>(null);

  const [overview, setOverview] = useState<OverviewOut | null>(null);
  const [quality, setQuality] = useState<QualityOut | null>(null);
  const [judge, setJudge] = useState<JudgeOut | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalOut | null>(null);
  const [performance, setPerformance] = useState<PerformanceOut | null>(null);
  const [cost, setCost] = useState<CostOut | null>(null);
  const [errors, setErrors] = useState<ErrorsOut | null>(null);
  const [safety, setSafety] = useState<SafetySummary | null>(null);
  const [trend, setTrend] = useState<TrendOut | null>(null);
  const [trendDays, setTrendDays] = useState(7);

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  useEffect(() => {
    if (!accessToken) return;
    getVersionFilters(accessToken).then(setVersionOptions).catch(() => { });
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) return;
    getSafetySummary(filters, accessToken)
      .then((d) => d && setSafety(d))
      .catch(() => { });
  }, [accessToken, filters]);

  useEffect(() => {
    if (!accessToken || (activeTab !== "quality" && activeTab !== "overview")) return;
    getTrend(filters, trendDays, accessToken)
      .then(setTrend)
      .catch(() => setTrend(null));
  }, [accessToken, activeTab, filters, trendDays]);

  const fetchTab = useCallback(
    async (isBackground: boolean = false) => {
      if (!accessToken) return;
      setIsRefreshing(true);
      setError(null);
      try {
        if (activeTab === "overview") {
          const [ovData, jData] = await Promise.all([
            getOverview(filters, accessToken),
            getJudge(filters, accessToken),
          ]);
          setOverview(ovData);
          setJudge(jData);
        }
        else if (activeTab === "quality") {
          const [qData, jData] = await Promise.all([
            getQuality(filters, accessToken),
            getJudge(filters, accessToken),
          ]);
          setQuality(qData);
          setJudge(jData);
        }
        else if (activeTab === "retrieval") setRetrieval(await getRetrieval(filters, accessToken));
        else if (activeTab === "performance") setPerformance(await getPerformance(filters, accessToken));
        else if (activeTab === "cost") setCost(await getCost(filters, accessToken));
        else if (activeTab === "errors") setErrors(await getErrors(filters, accessToken));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Lỗi không xác định");
      } finally {
        setIsRefreshing(false);
      }
    },
    [activeTab, filters, accessToken]
  );

  useEffect(() => {
    fetchTab(false);
  }, [fetchTab]);

  const handleFiltersChange = (newFilters: MonitoringFiltersInput) => {
    setFilters(newFilters);
    // Invalidate other tabs cache so they fetch fresh data with the new filter
    setOverview(null);
    setQuality(null);
    setRetrieval(null);
    setPerformance(null);
    setCost(null);
    setErrors(null);
  };

  const TABS_WITHOUT_FILTER: TabId[] = [];

  const currentTabHasData =
    (activeTab === "overview" && overview !== null) ||
    (activeTab === "quality" && quality !== null) ||
    (activeTab === "retrieval" && retrieval !== null) ||
    (activeTab === "performance" && performance !== null) ||
    (activeTab === "cost" && cost !== null) ||
    (activeTab === "errors" && errors !== null) ||
    TABS_WITHOUT_FILTER.includes(activeTab);

  const { intervalMs, setIntervalMs, lastRefreshedAt, isPollingActive, triggerUpdate } = useMonitoringPolling({
    defaultIntervalMs: 10000,
    onUpdate: () => {
      fetchTab(true);
      if (accessToken) {
        getVersionFilters(accessToken).then(setVersionOptions).catch(() => { });
      }
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl font-semibold">Giám sát RAG & AI — Dashboard Thống nhất</h1>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 rounded border bg-background px-2 py-1 text-xs">
                <span
                  className={`h-2 w-2 rounded-full ${isPollingActive ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/50"
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
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs hover:bg-accent"
            onClick={() => fetchTab(false)}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
            Làm mới
          </button>
        </div>
      </div>

      {/* Filter bar — hidden for tabs that don't need it */}
      {!TABS_WITHOUT_FILTER.includes(activeTab) && (
        <FilterBar filters={filters} setFilters={handleFiltersChange} options={versionOptions} />
      )}

      {/* Tab navigation */}
      <div className="flex flex-wrap gap-1 border-b overflow-x-auto">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm whitespace-nowrap ${isActive
                ? "border-primary font-semibold text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
        <Link
          href="/admin/monitoring/traces"
          className="ml-auto flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-primary hover:underline"
        >
          Trình khám phá dấu vết →
        </Link>
      </div>

      {/* Tab content */}
      {activeTab === "safety" ? (
        <SafetyTab accessToken={accessToken} filters={filters} />
      ) : !currentTabHasData ? (
        error ? (
          <ErrorState message={error} />
        ) : (
          <LoadingState />
        )
      ) : (
        <>
          {activeTab === "overview" && overview && (
            <OverviewTab
              data={overview}
              trend={trend}
              trendDays={trendDays}
              setTrendDays={setTrendDays}
              judgeData={judge}
              safety={safety}
              onNavigateTab={setActiveTab}
            />
          )}
          {activeTab === "quality" && quality && (
            <QualityTab
              data={quality}
              trend={trend}
              trendDays={trendDays}
              setTrendDays={setTrendDays}
              judgeData={judge}
              onNavigateTab={setActiveTab}
            />
          )}
          {activeTab === "retrieval" && retrieval && (
            <RetrievalTab data={retrieval} onNavigateTab={setActiveTab} />
          )}
          {activeTab === "performance" && performance && <PerformanceTab data={performance} />}
          {activeTab === "cost" && cost && <CostTab data={cost} />}
          {activeTab === "errors" && errors && (
            <ErrorsTab
              data={errors}
              onDrill={(code) => {
                setFilters({ ...filters, errorCode: code });
              }}
            />
          )}
        </>
      )}
    </div>
  );
}
