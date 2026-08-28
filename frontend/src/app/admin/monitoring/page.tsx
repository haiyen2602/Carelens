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
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { useAuth } from "@/lib/auth";
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
  { id: "quality", label: "Chất lượng", icon: Sparkles },
  { id: "retrieval", label: "Retrieval", icon: ScrollText },
  { id: "safety", label: "An toàn & Chuyển bác sĩ", icon: ShieldAlert },
  { id: "performance", label: "Hiệu năng", icon: Gauge },
  { id: "cost", label: "Token & Chi phí", icon: DollarSign },
  { id: "errors", label: "Lỗi", icon: AlertCircle },
  { id: "judge", label: "Judge", icon: ListChecks },
  { id: "golden", label: "Golden Evaluation", icon: Trophy },
  { id: "rag_chatbot", label: "RAG Chatbot", icon: Bot },
  { id: "versions", label: "So sánh Version", icon: Zap },
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
  label, metric, percent, suffix, help, sub, thresholdKey,
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
        <p className="mt-1 text-[11px] text-muted-foreground">{metric.reason ?? metric.status}</p>
      ) : null}
      {(metric?.scope || metric?.scope_note || metric?.note) && (
        <p className="mt-1 text-[10px] italic text-muted-foreground">
          {metric.scope ?? metric.scope_note ?? metric.note}
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
  label, value, target, unit = "%", drillTab, drillLabel,
}: {
  label: string;
  value: number;
  target: number;
  unit?: string;
  drillTab?: TabId;
  drillLabel?: string;
  onDrill?: () => void;
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
      {drillTab && drillLabel && (
        <span className="text-xs font-medium text-amber-700 underline cursor-pointer whitespace-nowrap">
          {drillLabel} →
        </span>
      )}
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
  return (
    <div className="surface-card p-4 text-sm text-muted-foreground">
      Dữ liệu hiện không khả dụng{reason ? ` (${reason})` : ""}. Không phải 0 — xem lại sau.
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

// ─── Tab: Overview ────────────────────────────────────────────────────────────

function OverviewTab({
  data,
  safety,
}: {
  data: OverviewOut;
  safety: SafetySummary | null;
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
          <WarningBanner label="Tỷ lệ thành công" value={successVal} target={THRESHOLDS.success_rate.target} drillTab="errors" drillLabel="Xem phân tích lỗi" />
        )}
        {errorVal !== null && errorVal > THRESHOLDS.error_rate.warn && (
          <WarningBanner label="Tỷ lệ lỗi" value={errorVal} target={THRESHOLDS.error_rate.target} drillTab="errors" drillLabel="Tìm hiểu lỗi" />
        )}
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Tổng số request" metric={{ value: total, status: "AVAILABLE" }} />
        <MetricCard label="Tỷ lệ thành công" metric={data.success_rate} percent thresholdKey="success_rate" />
        <MetricCard label="Tỷ lệ fallback" metric={data.fallback_rate} percent />
        <MetricCard label="Tỷ lệ lỗi" metric={data.error_rate} percent thresholdKey="error_rate" />
        <MetricCard label="Tỷ lệ timeout" metric={data.timeout_rate} percent />
        <MetricCard label="Tỷ lệ trả lời rỗng" metric={data.empty_reply_rate} percent />
        <MetricCard label="P50 latency" metric={data.latency_p50_ms} suffix="ms" />
        <MetricCard label="P95 latency" metric={data.latency_p95_ms} suffix="ms" />
        <MetricCard label="Token/query" metric={data.tokens_per_query} />
        <MetricCard label="Cost/query (USD)" metric={data.cost_per_query_usd} />
        <MetricCard label="Cost hôm nay (USD)" metric={data.daily_cost_usd} />
        <MetricCard label="Tỷ lệ ticket" metric={data.ticket_rate} percent />
        <MetricCard
          label="Tỷ lệ safety trigger"
          metric={data.safety_trigger_rate}
          percent
          help="Chỉ lọc theo khoảng ngày, không theo model/prompt_version nếu filter đang bật"
        />
        <MetricCard label="Tỷ lệ handoff" metric={data.handoff_rate} percent />
        <MetricCard label="Tỷ lệ được Judge chấm" metric={data.judged_rate} percent />
      </div>

      {/* Charts row */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="surface-card p-5">
          <DonutChart data={donutData} title="Phân bổ kết quả request" />
        </div>
        {safety && (
          <div className="surface-card p-5 space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-rose-500" /> An toàn (tóm tắt)
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-muted/40 p-3 text-center">
                <p className="text-xs text-muted-foreground">Safety triggers</p>
                <p className="text-2xl font-bold text-rose-600">{safety.safety_trigger_count ?? 0}</p>
              </div>
              <div className="rounded-lg bg-muted/40 p-3 text-center">
                <p className="text-xs text-muted-foreground">Handoff yêu cầu</p>
                <p className="text-2xl font-bold text-amber-600">{safety.handoff_required_count ?? 0}</p>
              </div>
              <div className="rounded-lg bg-muted/40 p-3 text-center col-span-2">
                <p className="text-xs text-muted-foreground">Tổng runs (cơ sở tính tỷ lệ)</p>
                <p className="text-xl font-semibold">{safety.denominator_agent_v2_total_runs ?? 0}</p>
              </div>
            </div>
            <Link href="/admin/monitoring" onClick={() => {}} className="text-xs text-primary underline">
              Xem chi tiết An toàn →
            </Link>
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
}: {
  data: QualityOut;
  trend: TrendOut | null;
  trendDays: number;
  setTrendDays: (d: number) => void;
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
            label="RAG Faithfulness"
            value={faithVal}
            target={THRESHOLDS.faithfulness.target}
            drillTab="rag_chatbot"
            drillLabel="Xem Worst Queries trong RAG Chatbot"
          />
        )}
        {relVal !== null && relVal < THRESHOLDS.answer_relevance.warn && (
          <WarningBanner
            label="Answer Relevance"
            value={relVal}
            target={THRESHOLDS.answer_relevance.target}
            drillTab="rag_chatbot"
            drillLabel="Xem Trace Explorer"
          />
        )}
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="RAG Faithfulness"
          metric={data.rag_faithfulness}
          thresholdKey="faithfulness"
          help="Tính trên trace trong buffer hiện tại (ring buffer)"
        />
        <MetricCard
          label="RAG Answer Relevance"
          metric={data.rag_answer_relevance}
          thresholdKey="answer_relevance"
          help="Tính trên trace trong buffer hiện tại (ring buffer)"
        />
        <DisabledMetricCard
          label="Golden HitRate@10"
          reason="Chưa hỗ trợ phiên này — không có stable retrieval_id contract"
          technicalNote="BUILD-31/35: retrieval_id không được persist durably. Cần migration để enable."
        />
        <DisabledMetricCard
          label="Golden MRR@10"
          reason="Chưa hỗ trợ phiên này — không có stable retrieval_id contract"
          technicalNote="BUILD-31/35: xem golden evaluation tab để theo dõi pass/fail."
        />
        <DisabledMetricCard
          label="Golden NDCG@10"
          reason="Chưa hỗ trợ phiên này — không có stable retrieval_id contract"
          technicalNote="BUILD-31/35: xem golden evaluation tab để theo dõi pass/fail."
        />
        <MetricCard label="Judge Overall Score" metric={data.judge_overall_score} help="Tín hiệu chất lượng phụ dựa trên LLM. Không phải xác nhận y khoa tuyệt đối." />
        <MetricCard
          label="Golden Pass Rate"
          metric={data.golden_pass_rate}
          percent
          sub={data.golden_pass_rate?.run_id ? `run ${data.golden_pass_rate.run_id.slice(0, 8)}` : undefined}
        />
        <MetricCard
          label="Regression Gate"
          metric={{ ...(data.regression_gate_status as MetricValue ?? {}), value: data.regression_gate_status?.value ?? null } as MetricValue}
        />
      </div>

      {/* Trend chart */}
      <div className="surface-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            Xu hướng Chất lượng ({trendDays} ngày qua)
          </h3>
          <div className="flex gap-1">
            {[7, 14, 30].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setTrendDays(d)}
                className={`rounded px-2.5 py-1 text-xs font-medium ${trendDays === d ? "bg-primary text-primary-foreground" : "border hover:bg-accent"}`}
              >
                {d}d
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

function RetrievalTab({ data }: { data: RetrievalOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;

  const gfVal = data.grounding_failure_rate?.status === "AVAILABLE" && typeof data.grounding_failure_rate.value === "number"
    ? data.grounding_failure_rate.value : null;

  const donutData = [
    { name: "Thành công RAG", value: data.rag_query_volume ?? 0, color: "#10b981" },
    { name: "Grounding failure", value: data.grounding_failure_rate?.numerator ?? 0, color: "#ef4444" },
  ];

  return (
    <div className="space-y-6">
      {gfVal !== null && gfVal > THRESHOLDS.grounding_failure_rate.warn && (
        <WarningBanner
          label="Grounding Failure Rate"
          value={gfVal}
          target={THRESHOLDS.grounding_failure_rate.target}
          drillTab="errors"
          drillLabel="Xem Errors tab"
        />
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="RAG query volume" metric={{ value: data.rag_query_volume ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Retrieval latency P50" metric={data.retrieval_latency_p50_ms} suffix="ms" />
        <MetricCard label="Retrieval latency P95" metric={data.retrieval_latency_p95_ms} suffix="ms" />
        <MetricCard
          label="Grounding failure rate"
          metric={data.grounding_failure_rate}
          percent
          thresholdKey="grounding_failure_rate"
          help="Tỷ lệ lỗi khi agent yêu cầu grounding nhưng không có tài liệu liên quan. KHÔNG isolable sang RAG riêng."
        />
        <DisabledMetricCard
          label="Empty retrieval rate"
          reason="Không đo được riêng cho RAG: GROUNDING_FAILURE bao nhiều intent (drug, prescription, dose), không thể tách RAG."
          technicalNote="Dùng grounding_failure_rate ở trên làm proxy."
        />
        <DisabledMetricCard
          label="Golden HitRate@10"
          reason="Không có stable retrieval_id contract (BUILD-31/35)"
          technicalNote="Cần persist retrieval_id trong AgentRunSpan để enable."
        />
        <DisabledMetricCard
          label="Golden MRR@10"
          reason="Không có stable retrieval_id contract (BUILD-31/35)"
        />
        <DisabledMetricCard
          label="Golden NDCG@10"
          reason="Không có stable retrieval_id contract (BUILD-31/35)"
        />
        <DisabledMetricCard
          label="Golden Precision@10"
          reason="Không có stable retrieval_id contract (BUILD-31/35)"
        />
      </div>

      <div className="surface-card p-5">
        <DonutChart data={donutData} title="RAG volume vs Grounding failures" />
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
          label="P95 Latency"
          value={p95Val / 1000}
          target={THRESHOLDS.p95_latency_ms.target / 1000}
          unit="s"
          drillTab="performance"
          drillLabel="Xem latency theo bước"
        />
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="End-to-end P50" metric={data.end_to_end_p50_ms} suffix="ms" />
        <MetricCard label="End-to-end P95" metric={data.end_to_end_p95_ms} suffix="ms" />
        <MetricCard label="End-to-end P99" metric={data.end_to_end_p99_ms} suffix="ms" />
        <MetricCard label="Tỷ lệ timeout" metric={data.timeout_rate} percent />
      </div>

      {stepBarData.length > 0 && (
        <HorizontalBarChart
          data={stepBarData}
          title="Latency P95 theo từng bước pipeline (ms)"
          valueFormatter={(v) => `${v}ms`}
        />
      )}

      {data.per_step && (
        <div className="surface-card overflow-x-auto p-4">
          <p className="mb-2 text-sm font-semibold">Chi tiết latency từng bước (span thật)</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="py-1">Bước</th><th>P50 (ms)</th><th>P95 (ms)</th><th>n</th>
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

  const modelBarData = data.by_model_usd
    ? Object.entries(data.by_model_usd)
        .map(([label, value]) => ({ label, value }))
        .sort((a, b) => b.value - a.value)
    : [];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Agent Cost (USD)" metric={data.agent_cost_usd} />
        <MetricCard label="Judge Cost (USD)" metric={data.judge_cost_usd} />
        <MetricCard label="Total Cost (USD)" metric={data.total_cost_usd} />
        <MetricCard label="Cost/query (USD)" metric={data.cost_per_query_usd} />
        <MetricCard label="Input tokens" metric={{ value: data.input_tokens ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Output tokens" metric={{ value: data.output_tokens ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Total tokens" metric={{ value: data.total_tokens ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Token/query" metric={data.tokens_per_query} />
      </div>

      {modelBarData.length > 0 && (
        <HorizontalBarChart
          data={modelBarData}
          title="Chi phí theo Model (USD)"
          valueFormatter={(v) => `$${v.toFixed(4)}`}
        />
      )}
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
          <DonutChart data={pieData} title="Phân bổ lỗi theo loại" />
        </div>
      )}
      <div className="surface-card overflow-x-auto p-4">
        <p className="mb-2 text-sm text-muted-foreground">
          Tổng số request: {data.total_requests ?? "N/A"}. Bấm 1 mã lỗi để lọc trace.
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-1">error_code</th><th>Tỷ lệ</th><th>Số lượng</th><th>Ghi chú</th>
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
                  <td className="text-[11px] italic text-muted-foreground">{m?.note ?? ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {data.unrecognized_error_codes && data.unrecognized_error_codes.length > 0 && (
          <p className="mt-2 text-xs text-amber-600">
            Mã lỗi chưa nằm trong danh sách chuẩn: {data.unrecognized_error_codes.join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}

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
        <MetricCard label="Tổng số đã enqueue" metric={{ value: data.total_judged ?? null, status: "AVAILABLE" }} />
        <MetricCard label="PENDING" metric={{ value: data.judged_pending ?? null, status: "AVAILABLE" }} />
        <MetricCard label="COMPLETED" metric={{ value: data.judged_completed ?? null, status: "AVAILABLE" }} />
        <MetricCard label="FAILED" metric={{ value: data.judged_failed ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Judge Cost (USD)" metric={data.judge_cost_usd} />
        <MetricCard label="Judge input tokens" metric={{ value: data.judge_input_tokens ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Judge output tokens" metric={{ value: data.judge_output_tokens ?? null, status: "AVAILABLE" }} />
      </div>

      {distData.length > 0 && (
        <div className="surface-card p-5">
          <DonutChart data={distData} title="Phân bổ điểm Judge (score distribution)" />
        </div>
      )}

      {data.disclaimer && <p className="text-xs italic text-muted-foreground">{data.disclaimer}</p>}

      {data.low_score_cases && data.low_score_cases.length > 0 && (
        <div className="surface-card overflow-x-auto p-4">
          <p className="mb-2 text-sm font-semibold">Case điểm thấp (&lt; 0.5)</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th>Trace</th><th>Path</th><th>Điểm</th>
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
        Chưa có golden run nào được persist. Chạy{" "}
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
          run_golden_evaluation.py --persist
        </code>{" "}
        để có dữ liệu.
      </div>
    );
  }
  const run = data.latest_run;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Golden set version" metric={{ value: run.golden_set_version, status: "AVAILABLE" }} />
        <MetricCard
          label="Pass rate"
          metric={{ value: run.pass_rate, status: run.pass_rate !== null ? "AVAILABLE" : "NOT_APPLICABLE" }}
          percent
        />
        <MetricCard
          label="Regression gate"
          metric={{ value: run.regression_gate_passed ? "PASS" : "FAIL", status: "AVAILABLE" }}
        />
        <MetricCard
          label="Số case"
          metric={{ value: `${run.passed_cases}/${run.total_cases}`, status: "AVAILABLE" }}
        />
      </div>
      <div className="surface-card p-4">
        <p className="mb-2 text-sm font-semibold">Theo category</p>
        <table className="w-full text-sm">
          <tbody>
            {Object.entries(run.by_category).map(([cat, v]) => (
              <tr key={cat} className="border-t">
                <td className="py-1">{cat}</td>
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
            Case fail: {run.failed_case_ids.join(", ")}
          </p>
        </div>
      )}
      <p className="text-xs italic text-muted-foreground">
        Lưu ý: category FALLBACK chưa có case E2E thật — xem BUILD-35 report.
      </p>
    </div>
  );
}

// ─── Tab: Versions ────────────────────────────────────────────────────────────

function VersionsTab({ accessToken }: { accessToken: string | null | undefined }) {
  const [section, setSection] = useState("overview");
  const [before, setBefore] = useState<MonitoringFiltersInput>({});
  const [after, setAfter] = useState<MonitoringFiltersInput>({});
  const [result, setResult] = useState<CompareOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
          <label className="text-xs text-muted-foreground">Section</label>
          <select
            className="rounded border bg-background px-2 py-1 text-sm"
            value={section}
            onChange={(e) => setSection(e.target.value)}
          >
            {["overview", "quality", "retrieval", "performance", "cost", "errors", "judge"].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        {(["Before model", "Before prompt_version", "After model", "After prompt_version"] as const).map((lbl) => {
          const isBefore = lbl.startsWith("Before");
          const field = lbl.includes("model") ? "model" : "promptVersion";
          const cur = isBefore ? before : after;
          const set = isBefore ? setBefore : setAfter;
          return (
            <div key={lbl} className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">{lbl}</label>
              <input
                className="rounded border bg-background px-2 py-1 text-sm"
                value={(cur as Record<string, string | undefined>)[field] ?? ""}
                onChange={(e) => set({ ...cur, [field]: e.target.value || undefined })}
              />
            </div>
          );
        })}
        <button
          type="button"
          className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground"
          onClick={run}
        >
          So sánh
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
    { id: "overview", label: "Tổng quan & Health" },
    { id: "retrieval", label: "Retrieval Quality" },
    { id: "generation", label: "Generation & Faithfulness" },
    { id: "safety", label: "An toàn & Sự cố Thuốc" },
    { id: "system", label: "Độ trễ & Pipeline" },
    { id: "traces", label: "Trace Explorer" },
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
          Live Real-time (10s)
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
          <option value="all">Chatbot Version: Tất cả</option>
          {filterOptions.chatbot_versions.map((v) => (
            <option key={v.value} value={v.value}>Chatbot Version: {v.label}</option>
          ))}
        </select>
        <select
          value={modelFilter}
          onChange={(e) => setModelFilter(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2.5 text-xs font-medium"
        >
          <option value="all">Model: Tất cả</option>
          {filterOptions.models.map((m) => <option key={m} value={m}>Model: {m}</option>)}
        </select>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          <span className="text-muted-foreground">RAG Status:</span>
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
              { label: "Faithfulness", value: metricPct(kpis.faithfulness), target: "≥ 85%", color: "emerald" },
              { label: "Answer Relevance", value: metricPct(kpis.answer_relevance), target: "≥ 80%", color: "blue" },
              { label: "P95 Latency", value: `${kpis.p95_latency_ms || 0}ms`, target: "E2E", color: "slate" },
              { label: "Sự cố An toàn", value: `${safetyData?.critical_safety_failures ?? 0} sự cố`, target: "Critical Gate", color: "emerald" },
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
                Xu hướng Chất lượng RAG (7 ngày)
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
              { label: "HitRate@10", val: retrievalData?.metrics?.hit_rate_10, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
              { label: "MRR@10", val: retrievalData?.metrics?.mrr_10, fmt: (v: number) => v.toFixed(2) },
              { label: "NDCG@10", val: retrievalData?.metrics?.ndcg_10, fmt: (v: number) => v.toFixed(2) },
              { label: "Tổng Chunks", val: retrievalData?.metrics?.total_indexed_chunks, fmt: (v: number) => String(v) },
            ].map(({ label, val, fmt }) => (
              <div key={label} className="surface-card p-5">
                <span className="text-xs font-semibold text-muted-foreground uppercase">{label}</span>
                <p className="mt-2 text-3xl font-extrabold text-primary">
                  {typeof val === "number" ? fmt(val) : "N/A"}
                </p>
                {typeof val !== "number" && (
                  <p className="mt-1 text-[10px] text-muted-foreground italic">Cần đủ trace để tính</p>
                )}
              </div>
            ))}
          </div>
          {(retrievalData?.worst_queries ?? []).length > 0 && (
            <div className="surface-card p-5">
              <h3 className="font-bold flex items-center gap-2 mb-3">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                Worst Queries (Retrieval thấp nhất)
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-sm text-left">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="py-2 px-3">Câu truy vấn</th>
                      <th className="py-2 px-3">Lượt</th>
                      <th className="py-2 px-3">Top-1</th>
                      <th className="py-2 px-3">Precision</th>
                      <th className="py-2 px-3">Recall</th>
                      <th className="py-2 px-3">Faithfulness</th>
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
            <h3 className="font-bold flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /> Chất lượng Generation</h3>
            {[
              { label: "Faithfulness", val: generationData?.metrics?.faithfulness },
              { label: "Answer Relevance", val: generationData?.metrics?.answer_relevance },
              { label: "Hallucination Rate", val: generationData?.metrics?.hallucination_rate },
              { label: "Abstention Accuracy", val: generationData?.metrics?.abstention_accuracy },
            ].map(({ label, val }) => (
              <div key={label} className="flex justify-between py-2 border-b border-border last:border-0 text-sm">
                <span className="text-muted-foreground">{label}</span>
                <span className="font-bold">{metricPct(val)}</span>
              </div>
            ))}
          </div>
          <div className="surface-card p-5 space-y-3">
            <h3 className="font-bold">Phân bổ theo Model</h3>
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
              { label: "Lỗi Liều lượng / Tần suất", val: safetyData?.dosage_consistency_failures ?? 0 },
              { label: "Tương tác thuốc nguy hiểm", val: safetyData?.interaction_unsupported_claims ?? 0 },
              { label: "Tổng Escalation trong DB", val: (safetyData?.incidents ?? []).length },
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
            <span className="text-xs text-muted-foreground">{traces.length} records</span>
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
                    <th className="py-3 px-4">Faithfulness</th>
                    <th className="py-3 px-4">Relevance</th>
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
                          {t.status}
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
  const [loading, setLoading] = useState(false);
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

  useEffect(() => {
    if (!accessToken) return;
    getVersionFilters(accessToken).then(setVersionOptions).catch(() => {});
    // Fetch safety summary for Overview card
    fetch(`${apiBase}/api/v1/admin/safety/summary`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setSafety(d))
      .catch(() => {});
  }, [accessToken, apiBase]);

  // Fetch trend whenever trendDays or filters change (and quality tab is active)
  useEffect(() => {
    if (!accessToken || activeTab !== "quality") return;
    getTrend(filters, trendDays, accessToken)
      .then(setTrend)
      .catch(() => setTrend(null));
  }, [accessToken, activeTab, filters, trendDays]);

  const fetchTab = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
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
      setLoading(false);
    }
  }, [activeTab, filters, accessToken]);

  useEffect(() => {
    fetchTab();
  }, [fetchTab]);

  const TABS_WITHOUT_FILTER: TabId[] = ["safety", "golden", "rag_chatbot", "versions"];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Giám sát RAG & AI — Dashboard Thống nhất</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Dữ liệu durable từ BUILD-32/33/34/35/36. Tất cả chỉ số N/A đều có lý do rõ ràng — không để trống.
          </p>
        </div>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs hover:bg-accent"
          onClick={fetchTab}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Làm mới
        </button>
      </div>

      {/* Filter bar — hidden for tabs that don't need it */}
      {!TABS_WITHOUT_FILTER.includes(activeTab) && (
        <FilterBar filters={filters} setFilters={setFilters} options={versionOptions} />
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
              className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm whitespace-nowrap ${
                isActive
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
        <div className="surface-card p-4 text-sm space-y-2">
          <h2 className="font-semibold flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-rose-500" /> An toàn & Chuyển bác sĩ
          </h2>
          <p>
            Dữ liệu Safety & Handoff dùng chung API đã có từ BUILD-34:{" "}
            <a className="text-primary underline" href="/api/v1/admin/safety/summary" target="_blank" rel="noreferrer">
              /admin/safety/summary
            </a>
            . Chi tiết từng event:{" "}
            <a className="text-primary underline" href="/api/v1/admin/safety/events" target="_blank" rel="noreferrer">
              /admin/safety/events
            </a>.
          </p>
          {safety && (
            <div className="grid grid-cols-3 gap-3 pt-2">
              <div className="rounded-lg border p-3 text-center">
                <p className="text-xs text-muted-foreground">Safety triggers</p>
                <p className="text-2xl font-bold text-rose-600">{safety.safety_trigger_count ?? 0}</p>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <p className="text-xs text-muted-foreground">Handoff yêu cầu</p>
                <p className="text-2xl font-bold text-amber-600">{safety.handoff_required_count ?? 0}</p>
              </div>
              <div className="rounded-lg border p-3 text-center">
                <p className="text-xs text-muted-foreground">Tổng Agent V2 runs</p>
                <p className="text-2xl font-bold">{safety.denominator_agent_v2_total_runs ?? 0}</p>
              </div>
            </div>
          )}
        </div>
      ) : activeTab === "rag_chatbot" ? (
        <RagChatbotTab accessToken={accessToken} />
      ) : activeTab === "versions" ? (
        <VersionsTab accessToken={accessToken} />
      ) : loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} />
      ) : (
        <>
          {activeTab === "overview" && overview && <OverviewTab data={overview} safety={safety} />}
          {activeTab === "quality" && quality && (
            <QualityTab data={quality} trend={trend} trendDays={trendDays} setTrendDays={setTrendDays} />
          )}
          {activeTab === "retrieval" && retrieval && <RetrievalTab data={retrieval} />}
          {activeTab === "performance" && performance && <PerformanceTab data={performance} />}
          {activeTab === "cost" && cost && <CostTab data={cost} />}
          {activeTab === "errors" && errors && (
            <ErrorsTab
              data={errors}
              onDrill={(code) => setFilters({ ...filters, errorCode: code })}
            />
          )}
          {activeTab === "judge" && judge && <JudgeTab data={judge} />}
          {activeTab === "golden" && golden && <GoldenTab data={golden} />}
        </>
      )}
    </div>
  );
}
