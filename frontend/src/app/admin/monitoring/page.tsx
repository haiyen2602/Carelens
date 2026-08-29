"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
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
  | "errors"
  | "judge"
  | "golden"
  | "rag_chatbot"
  | "versions";

const TABS: { id: TabId; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "Tổng quan", icon: Activity },
  { id: "quality", label: "Chất lượng AI & RAG", icon: Sparkles },
  { id: "retrieval", label: "Truy xuất (Retrieval)", icon: ScrollText },
  { id: "safety", label: "An toàn & Chuyển bác sĩ", icon: ShieldAlert },
  { id: "performance", label: "Hiệu năng & Độ trễ", icon: Gauge },
  { id: "cost", label: "Token & Chi phí", icon: DollarSign },
  { id: "errors", label: "Phân tích lỗi", icon: AlertCircle },
  { id: "judge", label: "Đánh giá tự động (Judge)", icon: ListChecks },
  { id: "golden", label: "Bộ dữ liệu chuẩn (Golden Set)", icon: Trophy },
  { id: "rag_chatbot", label: "Chatbot RAG chuyên sâu", icon: Bot },
  { id: "versions", label: "So sánh phiên bản", icon: Zap },
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
  opts: { percent?: boolean; suffix?: string } = {}
): string {
  if (!m || m.value === null || m.value === undefined || m.status !== "AVAILABLE")
    return "N/A";
  const v = typeof m.value === "number" ? m.value : Number(m.value);
  if (Number.isNaN(v)) return "N/A";
  if (opts.percent) return `${(v * 100).toFixed(1)}%`;
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
  help,
  sub,
  thresholdKey,
}: {
  label: string;
  metric?: MetricValue;
  percent?: boolean;
  suffix?: string;
  help?: string;
  sub?: string;
  thresholdKey?: keyof typeof THRESHOLDS;
}) {
  const display = formatMetric(metric, { percent, suffix });
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

function FilterBar({
  filters, setFilters, options,
}: {
  filters: MonitoringFiltersInput;
  setFilters: (f: MonitoringFiltersInput) => void;
  options: VersionFiltersOut | null;
}) {
  const set = (patch: Partial<MonitoringFiltersInput>) => setFilters({ ...filters, ...patch });
  return (
    <div className="surface-card flex flex-wrap items-end gap-3 p-4">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Từ ngày</label>
        <input
          type="date"
          className="rounded border bg-background px-2 py-1 text-sm"
          value={filters.dateFrom ?? ""}
          onChange={(e) => set({ dateFrom: e.target.value || undefined })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Đến ngày</label>
        <input
          type="date"
          className="rounded border bg-background px-2 py-1 text-sm"
          value={filters.dateTo ?? ""}
          onChange={(e) => set({ dateTo: e.target.value || undefined })}
        />
      </div>
      <FilterSelect label="Model" value={filters.model} options={options?.model ?? []} onChange={(v) => set({ model: v })} />
      <FilterSelect label="Prompt version" value={filters.promptVersion} options={options?.prompt_version ?? []} onChange={(v) => set({ promptVersion: v })} />
      <FilterSelect label="Retrieval version" value={filters.retrievalVersion} options={options?.retrieval_version ?? []} onChange={(v) => set({ retrievalVersion: v })} />
      <FilterSelect label="Execution path" value={filters.executionPath} options={options?.execution_path ?? []} onChange={(v) => set({ executionPath: v })} />
      <FilterSelect label="Error code" value={filters.errorCode} options={options?.error_code ?? []} onChange={(v) => set({ errorCode: v })} />
      <FilterSelect label="Judge model" value={filters.judgeModel} options={options?.judge_model ?? []} onChange={(v) => set({ judgeModel: v })} />
      <button
        type="button"
        className="ml-auto inline-flex items-center gap-1 rounded border px-3 py-1.5 text-xs hover:bg-accent"
        onClick={() => setFilters({})}
      >
        <RefreshCw className="h-3 w-3" /> Xoá bộ lọc
      </button>
    </div>
  );
}

function FilterSelect({
  label, value, options, onChange,
}: {
  label: string; value?: string; options: string[]; onChange: (v: string | undefined) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-muted-foreground">{label}</label>
      <select
        className="rounded border bg-background px-2 py-1 text-sm"
        value={value ?? "all"}
        onChange={(e) => onChange(e.target.value === "all" ? undefined : e.target.value)}
      >
        <option value="all">Tất cả</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
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
    faithfulness: p.faithfulness !== null ? Math.round(p.faithfulness * 100) : null,
    relevance: p.relevance !== null ? Math.round(p.relevance * 100) : null,
    faith_n: p.faithfulness_n,
    rel_n: p.relevance_n,
    requests: p.requests,
  }));
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="gFaith" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gRel" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#2563eb" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
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
              const n = name === "faithfulness" ? props.payload.faith_n : props.payload.rel_n;
              return [`${val}% (n=${n})`, name === "faithfulness" ? "Faithfulness" : "Answer Relevance"];
            }}
          />
          <Legend />
          <Area type="monotone" dataKey="faithfulness" name="Faithfulness" stroke="#10b981" strokeWidth={2} fill="url(#gFaith)" connectNulls />
          <Area type="monotone" dataKey="relevance" name="Answer Relevance" stroke="#2563eb" strokeWidth={2} fill="url(#gRel)" connectNulls />
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
  timeline: Array<{ timestamp: string; [model: string]: number | string }>;
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
  safety,
  onNavigateTab,
}: {
  data: OverviewOut;
  safety: SafetySummary | null;
  onNavigateTab: (tab: TabId) => void;
}) {
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const successVal = data.success_rate?.status === "AVAILABLE" && typeof data.success_rate.value === "number"
    ? data.success_rate.value : null;
  const errorVal = data.error_rate?.status === "AVAILABLE" && typeof data.error_rate.value === "number"
    ? data.error_rate.value : null;
  const fallbackVal = data.fallback_rate?.status === "AVAILABLE" && typeof data.fallback_rate.value === "number"
    ? data.fallback_rate.value : null;

  const total = data.total_requests ?? 0;
  const successN = successVal !== null ? Math.round(successVal * total) : 0;
  const errorN = errorVal !== null ? Math.round(errorVal * total) : 0;
  const fallbackN = fallbackVal !== null ? Math.round(fallbackVal * total) : 0;
  const otherN = Math.max(0, total - successN - errorN - fallbackN);

  const donutData = [
    { name: "Thành công", value: successN, color: "#10b981" },
    { name: "Lỗi", value: errorN, color: "#ef4444" },
    { name: "Fallback", value: fallbackN, color: "#f59e0b" },
    ...(otherN > 0 ? [{ name: "Khác", value: otherN, color: "#94a3b8" }] : []),
  ];

  return (
    <div className="space-y-6">
      {/* Warnings */}
      <div className="space-y-2">
        {successVal !== null && successVal < THRESHOLDS.success_rate.warn && (
          <WarningBanner
            label="Tỷ lệ thành công"
            value={successVal}
            target={THRESHOLDS.success_rate.target}
            drillTab="errors"
            drillLabel="Xem phân tích lỗi"
            onDrill={() => onNavigateTab("errors")}
          />
        )}
        {errorVal !== null && errorVal > THRESHOLDS.error_rate.warn && (
          <WarningBanner
            label="Tỷ lệ lỗi"
            value={errorVal}
            target={THRESHOLDS.error_rate.target}
            drillTab="errors"
            drillLabel="Tìm hiểu lỗi"
            onDrill={() => onNavigateTab("errors")}
          />
        )}
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Tổng lượt yêu cầu (Requests)" metric={{ value: total, status: "AVAILABLE" }} />
        <MetricCard label="Tỷ lệ thành công" metric={data.success_rate} percent thresholdKey="success_rate" />
        <MetricCard label="Tỷ lệ phản hồi dự phòng (Fallback)" metric={data.fallback_rate} percent />
        <MetricCard label="Tỷ lệ phát sinh lỗi (Error Rate)" metric={data.error_rate} percent thresholdKey="error_rate" />
        <MetricCard label="Tỷ lệ quá thời gian (Timeout)" metric={data.timeout_rate} percent />
        <MetricCard label="Tỷ lệ phản hồi rỗng (Empty Reply)" metric={data.empty_reply_rate} percent />
        <MetricCard label="Độ trễ trung vị P50 (Latency)" metric={data.latency_p50_ms} suffix="ms" />
        <MetricCard label="Độ trễ phân vị P95 (Latency)" metric={data.latency_p95_ms} suffix="ms" />
        <MetricCard label="Lượng Token / lượt yêu cầu" metric={data.tokens_per_query} />
        <MetricCard label="Chi phí trung bình / lượt (USD)" metric={data.cost_per_query_usd} />
        <MetricCard label="Tổng chi phí hôm nay (USD)" metric={data.daily_cost_usd} />
        <MetricCard label="Tỷ lệ tạo báo cáo (Ticket)" metric={data.ticket_rate} percent />
        <MetricCard
          label="Tỷ lệ kích hoạt an toàn (Safety)"
          metric={data.safety_trigger_rate}
          percent
          help="Chỉ lọc theo khoảng ngày, không theo model/prompt_version nếu filter đang bật"
        />
        <MetricCard label="Tỷ lệ chuyển bác sĩ (Handoff)" metric={data.handoff_rate} percent />
        <MetricCard label="Tỷ lệ qua Judge đánh giá" metric={data.judged_rate} percent />
      </div>

      {/* Charts row */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="surface-card p-5">
          <DonutChart data={donutData} title="Phân bổ trạng thái phản hồi" />
        </div>
        {safety && (
          <div className="surface-card p-5 space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-rose-500" /> An toàn & Chuyển tiếp bác sĩ (Tóm tắt)
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-muted/40 p-3 text-center">
                <p className="text-xs text-muted-foreground">Kích hoạt cảnh báo an toàn</p>
                <p className="text-2xl font-bold text-rose-600">{safety.safety_trigger_count ?? 0}</p>
              </div>
              <div className="rounded-lg bg-muted/40 p-3 text-center">
                <p className="text-xs text-muted-foreground">Yêu cầu chuyển bác sĩ</p>
                <p className="text-2xl font-bold text-amber-600">{safety.handoff_required_count ?? 0}</p>
              </div>
              <div className="rounded-lg bg-muted/40 p-3 text-center col-span-2">
                <p className="text-xs text-muted-foreground">Tổng số lượt chạy (Cơ sở tính)</p>
                <p className="text-xl font-semibold">{safety.denominator_agent_v2_total_runs ?? 0}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onNavigateTab("safety")}
              className="text-xs text-primary underline bg-transparent border-none p-0 cursor-pointer font-medium"
            >
              Xem chi tiết An toàn & Chuyển bác sĩ →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Tab: Quality ─────────────────────────────────────────────────────────────

function QualityTab({
  data,
  trend,
  trendDays,
  setTrendDays,
  onNavigateTab,
}: {
  data: QualityOut;
  trend: TrendOut | null;
  trendDays: number;
  setTrendDays: (d: number) => void;
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
            label="Độ trung thực (Faithfulness)"
            value={faithVal}
            target={THRESHOLDS.faithfulness.target}
            drillTab="rag_chatbot"
            drillLabel="Xem Worst Queries trong RAG Chatbot"
            onDrill={() => onNavigateTab("rag_chatbot")}
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

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
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
        <DisabledMetricCard
          label="Tỷ lệ tìm thấy Top 10 (HitRate@10)"
          reason="Chưa hỗ trợ phiên này — không có stable retrieval_id contract"
          technicalNote="BUILD-31/35: retrieval_id không được lưu dài hạn vào DB. Cần migration để kích hoạt."
        />
        <DisabledMetricCard
          label="Thứ hạng đảo trung bình (MRR@10)"
          reason="Chưa hỗ trợ phiên này — không có stable retrieval_id contract"
          technicalNote="BUILD-31/35: Xem tab Đánh giá chuẩn (Golden Set) để theo dõi đạt/không đạt."
        />
        <DisabledMetricCard
          label="Độ chuẩn tích lũy chiết khấu (NDCG@10)"
          reason="Chưa hỗ trợ phiên này — không có stable retrieval_id contract"
          technicalNote="BUILD-31/35: Xem tab Đánh giá chuẩn (Golden Set) để theo dõi đạt/không đạt."
        />
        <MetricCard label="Điểm đánh giá tổng thể (Judge Score)" metric={data.judge_overall_score} help="Tín hiệu đánh giá chất lượng tự động bằng LLM. Không phải xác nhận chuyên môn y khoa tuyệt đối." />
        <MetricCard
          label="Tỷ lệ đạt chuẩn (Golden Pass Rate)"
          metric={data.golden_pass_rate}
          percent
          sub={data.golden_pass_rate?.run_id ? `Lượt kiểm thử: ${data.golden_pass_rate.run_id.slice(0, 8)}` : undefined}
        />
        <MetricCard
          label="Cổng kiểm thử hồi quy (Regression Gate)"
          metric={{ ...(data.regression_gate_status as MetricValue ?? {}), value: data.regression_gate_status?.value ?? null } as MetricValue}
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

  const donutData = [
    { name: "Truy vấn RAG thành công", value: data.rag_query_volume ?? 0, color: "#10b981" },
    { name: "Lỗi thiếu căn cứ (Grounding Failure)", value: data.grounding_failure_rate?.numerator ?? 0, color: "#ef4444" },
  ];

  return (
    <div className="space-y-6">
      {gfVal !== null && gfVal > THRESHOLDS.grounding_failure_rate.warn && (
        <WarningBanner
          label="Tỷ lệ lỗi thiếu căn cứ (Grounding Failure)"
          value={gfVal}
          target={THRESHOLDS.grounding_failure_rate.target}
          drillTab="errors"
          drillLabel="Xem phân tích lỗi chi tiết"
          onDrill={() => onNavigateTab("errors")}
        />
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Số lượt truy vấn RAG (Query Volume)" metric={{ value: data.rag_query_volume ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Độ trễ truy xuất P50 (Retrieval)" metric={data.retrieval_latency_p50_ms} suffix="ms" />
        <MetricCard label="Độ trễ truy xuất P95 (Retrieval)" metric={data.retrieval_latency_p95_ms} suffix="ms" />
        <MetricCard
          label="Tỷ lệ lỗi thiếu căn cứ (Grounding Failure)"
          metric={data.grounding_failure_rate}
          percent
          thresholdKey="grounding_failure_rate"
          help="Tỷ lệ yêu cầu cần căn cứ tài liệu y khoa nhưng không tìm thấy thông tin phù hợp."
        />
        <DisabledMetricCard
          label="Tỷ lệ truy xuất rỗng (Empty Retrieval)"
          reason="Không thể bóc tách riêng cho RAG: GROUNDING_FAILURE bao gồm nhiều intent (tra cứu thuốc, đơn thuốc, liều lượng)."
          technicalNote="Sử dụng chỉ số Grounding Failure Rate ở trên làm đối trọng."
        />
        <DisabledMetricCard
          label="Tỷ lệ tìm thấy Top 10 (HitRate@10)"
          reason="Chưa hỗ trợ ID truy xuất cố định (BUILD-31/35)"
          technicalNote="Cần lưu retrieval_id vào bảng AgentRunSpan để kích hoạt."
        />
        <DisabledMetricCard
          label="Thứ hạng đảo trung bình (MRR@10)"
          reason="Chưa hỗ trợ ID truy xuất cố định (BUILD-31/35)"
        />
        <DisabledMetricCard
          label="Độ chuẩn tích lũy chiết khấu (NDCG@10)"
          reason="Chưa hỗ trợ ID truy xuất cố định (BUILD-31/35)"
        />
        <DisabledMetricCard
          label="Độ chính xác Top 10 (Precision@10)"
          reason="Chưa hỗ trợ ID truy xuất cố định (BUILD-31/35)"
        />
      </div>

      <div className="surface-card p-5">
        <DonutChart data={donutData} title="Tỷ lệ truy vấn RAG so với lỗi Grounding" />
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
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Chi phí mô hình Agent (USD)" metric={data.agent_cost_usd} />
        <MetricCard label="Chi phí mô hình Judge (USD)" metric={data.judge_cost_usd} />
        <MetricCard label="Tổng chi phí sử dụng (USD)" metric={data.total_cost_usd} />
        <MetricCard label="Chi phí trung bình / lượt (USD)" metric={data.cost_per_query_usd} />
        <MetricCard label="Token đầu vào (Input Tokens)" metric={{ value: data.input_tokens ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Token đầu ra (Output Tokens)" metric={{ value: data.output_tokens ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Tổng lượng Token tiêu thụ" metric={{ value: data.total_tokens ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Lượng Token / lượt yêu cầu" metric={data.tokens_per_query} />
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
      name: code,
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
              <th className="py-1">Mã lỗi (Error Code)</th><th>Tỷ lệ phát sinh</th><th>Số lượng ca</th><th>Ghi chú kỹ thuật</th>
            </tr>
          </thead>
          <tbody>
            {KNOWN_ERROR_CODES_ORDER.map((code) => {
              const m = data.breakdown?.[code];
              const count = m?.numerator ?? 0;
              return (
                <tr
                  key={code}
                  className={`cursor-pointer border-t hover:bg-accent/50 ${count > 0 ? "" : "opacity-50"}`}
                  onClick={() => onDrill(code)}
                >
                  <td className="py-1 font-mono text-xs">{code}</td>
                  <td>{formatMetric(m, { percent: true })}</td>
                  <td className={count > 0 ? "font-semibold text-rose-600" : ""}>{m?.numerator ?? "N/A"}</td>
                  <td className="text-[11px] italic text-muted-foreground">{formatHumanNote(m?.note) ?? ""}</td>
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

// ─── Tab: Judge ───────────────────────────────────────────────────────────────

// ─── Tab: Judge ───────────────────────────────────────────────────────────────

function JudgeTab({ data }: { data: JudgeOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const distData = data.overall_score_distribution
    ? Object.entries(data.overall_score_distribution).map(([name, value], idx) => ({
      name,
      value,
      color: CHART_COLORS[idx % CHART_COLORS.length],
    }))
    : [];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Tổng lượt đưa vào chấm điểm" metric={{ value: data.total_judged ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Đang chờ chấm (Pending)" metric={{ value: data.judged_pending ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Đã chấm xong (Completed)" metric={{ value: data.judged_completed ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Chấm điểm thất bại (Failed)" metric={{ value: data.judged_failed ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Chi phí mô hình Judge (USD)" metric={data.judge_cost_usd} />
        <MetricCard label="Token đầu vào Judge (Input Tokens)" metric={{ value: data.judge_input_tokens ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Token đầu ra Judge (Output Tokens)" metric={{ value: data.judge_output_tokens ?? null, status: "AVAILABLE" }} />
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
                <th>Mã Trace (Trace ID)</th><th>Đường dẫn xử lý (Execution Path)</th><th>Điểm số</th>
              </tr>
            </thead>
            <tbody>
              {data.low_score_cases.map((c) => (
                <tr key={c.judge_id} className="border-t">
                  <td className="py-1">
                    <Link className="text-primary underline" href={`/admin/monitoring/traces/${c.trace_id}`}>
                      {c.trace_id?.slice(0, 8)}
                    </Link>
                  </td>
                  <td>{c.execution_path ?? "N/A"}</td>
                  <td className="font-semibold text-rose-600">{c.score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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

function SafetyTab({ accessToken }: { accessToken: string | null | undefined }) {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const [summary, setSummary] = useState<SafetySummaryFull | null>(null);
  const [events, setEvents] = useState<SafetyEventItem[]>([]);
  const [totalEvents, setTotalEvents] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const fetchSafety = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const headers = { Authorization: `Bearer ${accessToken}` };
      const [sumRes, evRes] = await Promise.all([
        fetch(`${apiBase}/api/v1/admin/safety/summary`, { headers }),
        fetch(`${apiBase}/api/v1/admin/safety/events?limit=50`, { headers }),
      ]);
      if (sumRes.ok) {
        setSummary(await sumRes.json());
      }
      if (evRes.ok) {
        const evData = await evRes.json();
        setEvents(evData.items ?? []);
        setTotalEvents(evData.total ?? 0);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi khi tải dữ liệu an toàn");
    } finally {
      setLoading(false);
    }
  }, [accessToken, apiBase]);

  useEffect(() => {
    fetchSafety();
  }, [fetchSafety]);

  const severityPie = summary?.severity_distribution
    ? Object.entries(summary.severity_distribution)
      .map(([name, value], idx) => ({
        name,
        value,
        color: name === "CRITICAL" ? "#ef4444" : name === "HIGH" ? "#f97316" : name === "MEDIUM" ? "#f59e0b" : "#10b981",
      }))
      .filter((d) => d.value > 0)
    : [];

  const reasonPie = summary?.reason_code_distribution
    ? Object.entries(summary.reason_code_distribution)
      .map(([name, value], idx) => ({
        name: formatHumanNote(name) ?? name,
        value,
        color: CHART_COLORS[idx % CHART_COLORS.length],
      }))
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
              sub={summary.safety_trigger_rate !== null && summary.safety_trigger_rate !== undefined ? `Tỷ lệ: ${(summary.safety_trigger_rate * 100).toFixed(2)}%` : undefined}
            />
            <MetricCard
              label="Yêu cầu chuyển bác sĩ (Handoff)"
              metric={{ value: summary.handoff_required_count ?? 0, status: "AVAILABLE" }}
              sub={summary.handoff_required_rate !== null && summary.handoff_required_rate !== undefined ? `Tỷ lệ: ${(summary.handoff_required_rate * 100).toFixed(2)}%` : undefined}
            />
            <MetricCard
              label="Đã tạo yêu cầu chuyển tiếp"
              metric={{ value: summary.handoff_created_count ?? 0, status: "AVAILABLE" }}
              sub={summary.handoff_created_rate !== null && summary.handoff_created_rate !== undefined ? `Tỷ lệ thành công: ${(summary.handoff_created_rate * 100).toFixed(1)}%` : undefined}
            />
            <MetricCard
              label="Chuyển tiếp bác sĩ thất bại"
              metric={{ value: summary.handoff_failure_count ?? 0, status: "AVAILABLE" }}
            />
            <MetricCard
              label="Yêu cầu chưa xử lý xong"
              metric={{ value: summary.unresolved_handoff_count ?? 0, status: "AVAILABLE" }}
            />
            <MetricCard
              label="Thời gian duyệt trung bình"
              metric={{ value: summary.time_to_review_avg_seconds ? `${Math.round(summary.time_to_review_avg_seconds)}s` : "Chưa có", status: "AVAILABLE" }}
              sub={summary.time_to_review_sample_count ? `${summary.time_to_review_sample_count} ca đã duyệt` : undefined}
            />
            <MetricCard
              label="Tổng lượt chạy Agent V2"
              metric={{ value: summary.denominator_agent_v2_total_runs ?? 0, status: "AVAILABLE" }}
              help="Cơ sở mẫu chuẩn (Denominator) dùng để tính tỷ lệ an toàn."
            />
            <MetricCard
              label="Ca chuyển tiếp cũ (Legacy)"
              metric={{ value: summary.legacy_escalation_count ?? 0, status: "AVAILABLE" }}
              help="Dữ liệu từ bảng Escalation cũ, không tính trùng vào Agent V2."
            />
          </div>

          {/* Charts */}
          <div className="grid gap-4 md:grid-cols-2">
            {severityPie.length > 0 ? (
              <div className="surface-card p-5">
                <DonutChart data={severityPie} title="Phân bổ mức độ nghiêm trọng (Severity)" />
              </div>
            ) : (
              <div className="surface-card p-5 flex items-center justify-center text-xs text-muted-foreground">
                Chưa có sự kiện phân loại mức độ nghiêm trọng
              </div>
            )}
            {reasonPie.length > 0 ? (
              <div className="surface-card p-5">
                <DonutChart data={reasonPie} title="Phân bổ nguyên nhân an toàn (Reason Codes)" />
              </div>
            ) : (
              <div className="surface-card p-5 flex items-center justify-center text-xs text-muted-foreground">
                Chưa có sự kiện phân loại mã lý do
              </div>
            )}
          </div>

          {/* Safety Events Table */}
          <div className="surface-card overflow-hidden">
            <div className="p-4 border-b flex items-center justify-between flex-wrap gap-2">
              <div>
                <h3 className="font-bold flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-rose-500" />
                  Danh sách sự kiện an toàn & Chuyển bác sĩ thực tế
                </h3>
                <p className="text-xs text-muted-foreground">
                  Tổng số: {totalEvents} sự kiện (hiển thị 50 sự kiện gần nhất)
                </p>
              </div>
              <button
                type="button"
                onClick={fetchSafety}
                className="flex items-center gap-1.5 rounded border px-3 py-1 text-xs hover:bg-accent"
              >
                <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
                Làm mới
              </button>
            </div>
            {events.length === 0 ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                Hệ thống chưa ghi nhận sự kiện an toàn nào cần xử lý.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[800px] text-sm text-left">
                  <thead>
                    <tr className="border-b bg-muted/50 text-xs text-muted-foreground">
                      <th className="py-3 px-4">Mã sự kiện (Event ID)</th>
                      <th className="py-3 px-4">Mã Trace</th>
                      <th className="py-3 px-4">Mức độ</th>
                      <th className="py-3 px-4">Nguyên nhân (Reason Code)</th>
                      <th className="py-3 px-4">Handoff Bác sĩ</th>
                      <th className="py-3 px-4">Trạng thái Handoff</th>
                      <th className="py-3 px-4">Thời gian</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {events.map((ev) => {
                      const sevColor =
                        ev.severity === "CRITICAL"
                          ? "bg-rose-50 text-rose-700 border-rose-200"
                          : ev.severity === "HIGH"
                            ? "bg-orange-50 text-orange-700 border-orange-200"
                            : ev.severity === "MEDIUM"
                              ? "bg-amber-50 text-amber-700 border-amber-200"
                              : "bg-emerald-50 text-emerald-700 border-emerald-200";

                      return (
                        <tr key={ev.id} className="hover:bg-muted/30">
                          <td className="py-3 px-4 font-mono text-xs font-semibold">{ev.id.slice(0, 8)}</td>
                          <td className="py-3 px-4 font-mono text-xs">
                            {ev.trace_id ? (
                              <Link
                                className="text-primary underline font-semibold"
                                href={`/admin/monitoring/traces/${ev.trace_id}`}
                              >
                                {ev.trace_id.slice(0, 8)}
                              </Link>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="py-3 px-4">
                            <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border ${sevColor}`}>
                              {ev.severity}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-xs font-medium">
                            {formatHumanNote(ev.reason_code) ?? ev.reason_code}
                          </td>
                          <td className="py-3 px-4 text-xs">
                            {ev.handoff_created ? (
                              <span className="text-emerald-600 font-semibold">Đã tạo yêu cầu</span>
                            ) : ev.handoff_required ? (
                              <span className="text-rose-600 font-semibold">Cần tạo</span>
                            ) : (
                              <span className="text-muted-foreground">Không yêu cầu</span>
                            )}
                          </td>
                          <td className="py-3 px-4 text-xs">
                            {ev.handoff_status_live ? (
                              <span className="rounded bg-muted px-2 py-0.5 font-mono text-[11px]">
                                {ev.handoff_status_live}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="py-3 px-4 text-xs text-muted-foreground">
                            {ev.created_at
                              ? new Date(ev.created_at).toLocaleString("vi-VN", {
                                timeZone: "Asia/Ho_Chi_Minh",
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                                day: "2-digit",
                                month: "2-digit",
                                year: "numeric",
                              })
                              : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ─── Safety Summary type ──────────────────────────────────────────────────────


interface SafetySummary {
  safety_trigger_count?: number;
  handoff_required_count?: number;
  denominator_agent_v2_total_runs?: number;
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AdminMonitoringPage() {
  const { accessToken } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [filters, setFilters] = useState<MonitoringFiltersInput>({});
  const [versionOptions, setVersionOptions] = useState<VersionFiltersOut | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trendDays, setTrendDays] = useState(7);

  const [overview, setOverview] = useState<OverviewOut | null>(null);
  const [quality, setQuality] = useState<QualityOut | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalOut | null>(null);
  const [performance, setPerformance] = useState<PerformanceOut | null>(null);
  const [cost, setCost] = useState<CostOut | null>(null);
  const [errors, setErrors] = useState<ErrorsOut | null>(null);
  const [judge, setJudge] = useState<JudgeOut | null>(null);
  const [golden, setGolden] = useState<GoldenOut | null>(null);
  const [trend, setTrend] = useState<TrendOut | null>(null);
  const [safety, setSafety] = useState<SafetySummary | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const TABS_WITHOUT_FILTER: TabId[] = ["safety", "golden", "rag_chatbot", "versions"];

  const currentTabHasData =
    (activeTab === "overview" && overview !== null) ||
    (activeTab === "quality" && quality !== null) ||
    (activeTab === "retrieval" && retrieval !== null) ||
    (activeTab === "performance" && performance !== null) ||
    (activeTab === "cost" && cost !== null) ||
    (activeTab === "errors" && errors !== null) ||
    (activeTab === "judge" && judge !== null) ||
    (activeTab === "golden" && golden !== null) ||
    TABS_WITHOUT_FILTER.includes(activeTab);

  useEffect(() => {
    if (!accessToken) return;
    getVersionFilters(accessToken).then(setVersionOptions).catch(() => { });
    // Fetch safety summary for Overview card
    fetch(`${apiBase}/api/v1/admin/safety/summary`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setSafety(d))
      .catch(() => { });
  }, [accessToken, apiBase]);

  // Fetch trend whenever trendDays or filters change (and quality tab is active)
  useEffect(() => {
    if (!accessToken || activeTab !== "quality") return;
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
        if (activeTab === "overview") setOverview(await getOverview(filters, accessToken));
        else if (activeTab === "quality") setQuality(await getQuality(filters, accessToken));
        else if (activeTab === "retrieval") setRetrieval(await getRetrieval(filters, accessToken));
        else if (activeTab === "performance") setPerformance(await getPerformance(filters, accessToken));
        else if (activeTab === "cost") setCost(await getCost(filters, accessToken));
        else if (activeTab === "errors") setErrors(await getErrors(filters, accessToken));
        else if (activeTab === "judge") setJudge(await getJudge(filters, accessToken));
        else if (activeTab === "golden") setGolden(await getGolden(undefined, accessToken));
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
    setJudge(null);
    setGolden(null);
  };

  const { intervalMs, setIntervalMs, lastRefreshedAt, isPollingActive, triggerUpdate } = useMonitoringPolling({
    defaultIntervalMs: 10000,
    onUpdate: () => {
      fetchTab(true);
      if (accessToken) {
        getVersionFilters(accessToken).then(setVersionOptions).catch(() => {});
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
          className="ml-auto flex items-center gap-1.5 px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
        >
          Trace Explorer →
        </Link>
      </div>

      {/* Tab content */}
      {activeTab === "safety" ? (
        <SafetyTab accessToken={accessToken} />
      ) : activeTab === "rag_chatbot" ? (
        <RagChatbotTab accessToken={accessToken} />
      ) : activeTab === "versions" ? (
        <VersionsTab accessToken={accessToken} versionOptions={versionOptions} />
      ) : !currentTabHasData ? (
        error ? (
          <ErrorState message={error} />
        ) : (
          <LoadingState />
        )
      ) : (
        <>
          {activeTab === "overview" && overview && (
            <OverviewTab data={overview} safety={safety} onNavigateTab={setActiveTab} />
          )}
          {activeTab === "quality" && quality && (
            <QualityTab
              data={quality}
              trend={trend}
              trendDays={trendDays}
              setTrendDays={setTrendDays}
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
          {activeTab === "judge" && judge && <JudgeTab data={judge} />}
          {activeTab === "golden" && golden && <GoldenTab data={golden} />}
        </>
      )}
    </div>
  );
}
