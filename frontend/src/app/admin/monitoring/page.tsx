"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  DollarSign,
  Gauge,
  ListChecks,
  Loader2,
  RefreshCw,
  ScrollText,
  ShieldAlert,
  Sparkles,
  Trophy,
  Zap,
} from "lucide-react";
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
  type VersionFiltersOut,
} from "@/lib/admin-monitoring";

type TabId = "overview" | "quality" | "retrieval" | "safety" | "performance" | "cost" | "errors" | "judge" | "golden" | "versions";

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
  { id: "versions", label: "So sánh Version", icon: Zap },
];

// spec §18: N/A must render as the literal text "N/A", never "0%"/"0.00".
function formatMetric(m: MetricValue | undefined, opts: { percent?: boolean; suffix?: string } = {}): string {
  if (!m || m.value === null || m.value === undefined || m.status !== "AVAILABLE") return "N/A";
  const v = typeof m.value === "number" ? m.value : Number(m.value);
  if (Number.isNaN(v)) return "N/A";
  if (opts.percent) return `${(v * 100).toFixed(1)}%`;
  return `${v.toFixed(v < 10 ? 3 : 2)}${opts.suffix ?? ""}`;
}

function metricTypeBadge(type?: MetricValue["metric_type"]) {
  if (!type) return null;
  const tone: Record<string, string> = {
    LIVE: "bg-emerald-500/10 text-emerald-600",
    GOLDEN: "bg-amber-500/10 text-amber-600",
    HEURISTIC: "bg-sky-500/10 text-sky-600",
    LLM_JUDGE: "bg-violet-500/10 text-violet-600",
    DETERMINISTIC: "bg-slate-500/10 text-slate-600",
  };
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${tone[type] ?? "bg-muted"}`}>{type}</span>;
}

function MetricCard({
  label, metric, percent, suffix, help, sub,
}: {
  label: string; metric?: MetricValue; percent?: boolean; suffix?: string; help?: string; sub?: string;
}) {
  const display = formatMetric(metric, { percent, suffix });
  return (
    <div className="surface-card p-4" title={help}>
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{label}</p>
        {metricTypeBadge(metric?.metric_type)}
      </div>
      <p className="mt-1 text-2xl font-semibold">{display}</p>
      {metric && metric.status === "AVAILABLE" && metric.numerator != null && metric.denominator != null ? (
        <p className="mt-1 text-[11px] text-muted-foreground">
          {metric.numerator} / {metric.denominator}
          {metric.sample_count != null ? ` (n=${metric.sample_count})` : ""}
        </p>
      ) : metric && metric.status !== "AVAILABLE" ? (
        <p className="mt-1 text-[11px] text-muted-foreground">{metric.reason ?? metric.status}</p>
      ) : null}
      {(metric?.scope || metric?.scope_note || metric?.note) && (
        <p className="mt-1 text-[10px] italic text-muted-foreground">{metric.scope ?? metric.scope_note ?? metric.note}</p>
      )}
      {sub && <p className="mt-1 text-[11px] text-muted-foreground">{sub}</p>}
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
      Dữ liệu hiện không khả dụng{reason ? ` (${reason})` : ""}. Không phải 0 -- xem lại sau.
    </div>
  );
}

function FilterBar({
  filters, setFilters, options,
}: {
  filters: MonitoringFiltersInput; setFilters: (f: MonitoringFiltersInput) => void; options: VersionFiltersOut | null;
}) {
  const set = (patch: Partial<MonitoringFiltersInput>) => setFilters({ ...filters, ...patch });
  return (
    <div className="surface-card flex flex-wrap items-end gap-3 p-4">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Từ ngày</label>
        <input type="date" className="rounded border bg-background px-2 py-1 text-sm" value={filters.dateFrom ?? ""} onChange={(e) => set({ dateFrom: e.target.value || undefined })} />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Đến ngày</label>
        <input type="date" className="rounded border bg-background px-2 py-1 text-sm" value={filters.dateTo ?? ""} onChange={(e) => set({ dateTo: e.target.value || undefined })} />
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

function FilterSelect({ label, value, options, onChange }: { label: string; value?: string; options: string[]; onChange: (v: string | undefined) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-muted-foreground">{label}</label>
      <select
        className="rounded border bg-background px-2 py-1 text-sm"
        value={value ?? "all"}
        onChange={(e) => onChange(e.target.value === "all" ? undefined : e.target.value)}
      >
        <option value="all">Tất cả</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}

function OverviewTab({ data }: { data: OverviewOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <MetricCard label="Tổng số request" metric={{ value: data.total_requests ?? null, status: "AVAILABLE" }} />
      <MetricCard label="Tỷ lệ thành công" metric={data.success_rate} percent />
      <MetricCard label="Tỷ lệ fallback" metric={data.fallback_rate} percent />
      <MetricCard label="Tỷ lệ lỗi" metric={data.error_rate} percent />
      <MetricCard label="Tỷ lệ timeout" metric={data.timeout_rate} percent />
      <MetricCard label="Tỷ lệ trả lời rỗng" metric={data.empty_reply_rate} percent />
      <MetricCard label="P50 latency" metric={data.latency_p50_ms} suffix="ms" />
      <MetricCard label="P95 latency" metric={data.latency_p95_ms} suffix="ms" />
      <MetricCard label="Token/query" metric={data.tokens_per_query} />
      <MetricCard label="Cost/query (USD)" metric={data.cost_per_query_usd} />
      <MetricCard label="Cost hôm nay (USD)" metric={data.daily_cost_usd} />
      <MetricCard label="Tỷ lệ ticket" metric={data.ticket_rate} percent />
      <MetricCard label="Tỷ lệ safety trigger" metric={data.safety_trigger_rate} percent help="Chỉ lọc theo khoảng ngày, không theo model/prompt_version nếu các filter đó đang bật" />
      <MetricCard label="Tỷ lệ handoff" metric={data.handoff_rate} percent />
      <MetricCard label="Tỷ lệ được Judge chấm" metric={data.judged_rate} percent />
    </div>
  );
}

function QualityTab({ data }: { data: QualityOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <MetricCard label="RAG Faithfulness" metric={data.rag_faithfulness} help="Chỉ tính trên trace còn trong buffer 200 mục gần nhất của tiến trình hiện tại" />
      <MetricCard label="RAG Answer Relevance" metric={data.rag_answer_relevance} help="Chỉ tính trên trace còn trong buffer 200 mục gần nhất của tiến trình hiện tại" />
      <MetricCard label="Golden HitRate@10" metric={data.golden_hit_rate_at_10} />
      <MetricCard label="Golden MRR@10" metric={data.golden_mrr_at_10} />
      <MetricCard label="Golden NDCG@10" metric={data.golden_ndcg_at_10} />
      <MetricCard label="Judge Overall Score" metric={data.judge_overall_score} help="Tín hiệu chất lượng phụ dựa trên LLM. Không phải xác nhận y khoa tuyệt đối." />
      <MetricCard label="Golden Pass Rate" metric={data.golden_pass_rate} percent sub={data.golden_pass_rate?.run_id ? `run ${data.golden_pass_rate.run_id}` : undefined} />
      <MetricCard label="Regression Gate" metric={{ ...data.regression_gate_status, value: data.regression_gate_status?.value ?? null } as MetricValue} />
    </div>
  );
}

function RetrievalTab({ data }: { data: RetrievalOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <MetricCard label="RAG query volume" metric={{ value: data.rag_query_volume ?? null, status: "AVAILABLE" }} />
      <MetricCard label="Retrieval latency P50" metric={data.retrieval_latency_p50_ms} suffix="ms" />
      <MetricCard label="Retrieval latency P95" metric={data.retrieval_latency_p95_ms} suffix="ms" />
      <MetricCard label="Empty retrieval rate" metric={data.empty_retrieval_rate} percent />
      <MetricCard label="Grounding failure rate" metric={data.grounding_failure_rate} percent />
      <MetricCard label="Golden HitRate@10" metric={data.golden_hit_rate_at_10} />
      <MetricCard label="Golden MRR@10" metric={data.golden_mrr_at_10} />
      <MetricCard label="Golden NDCG@10" metric={data.golden_ndcg_at_10} />
      <MetricCard label="Golden Precision@10" metric={data.golden_precision_at_10} />
      {data.citation_count_scope && <p className="col-span-full text-xs italic text-muted-foreground">Citation count: {data.citation_count_scope}</p>}
    </div>
  );
}

function PerformanceTab({ data }: { data: PerformanceOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="End-to-end P50" metric={data.end_to_end_p50_ms} suffix="ms" />
        <MetricCard label="End-to-end P95" metric={data.end_to_end_p95_ms} suffix="ms" />
        <MetricCard label="End-to-end P99" metric={data.end_to_end_p99_ms} suffix="ms" />
        <MetricCard label="Tỷ lệ timeout" metric={data.timeout_rate} percent />
      </div>
      {data.per_step && (
        <div className="surface-card overflow-x-auto p-4">
          <p className="mb-2 text-sm font-medium">Latency theo từng bước (span thật, BUILD-32)</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="py-1">Bước</th><th>P50 (ms)</th><th>P95 (ms)</th><th>n</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.per_step).map(([step, v]) => (
                <tr key={step} className="border-t">
                  <td className="py-1">{step}</td>
                  <td>{formatMetric(v[50], { suffix: "ms" })}</td>
                  <td>{formatMetric(v[95], { suffix: "ms" })}</td>
                  <td>{v[50]?.sample_count ?? "N/A"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CostTab({ data }: { data: CostOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;
  return (
    <div className="space-y-4">
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
      {data.by_model_usd && Object.keys(data.by_model_usd).length > 0 && (
        <div className="surface-card p-4">
          <p className="mb-2 text-sm font-medium">Chi phí theo model</p>
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(data.by_model_usd).map(([model, cost]) => (
                <tr key={model} className="border-t">
                  <td className="py-1">{model}</td>
                  <td className="text-right">${cost.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const KNOWN_ERROR_CODES_ORDER = [
  "BUDGET_EXCEEDED", "MODEL_ERROR", "MODEL_TIMEOUT", "TOOL_ERROR", "TOOL_TIMEOUT",
  "RETRIEVAL_ERROR", "RETRIEVAL_TIMEOUT", "REQUEST_TIMEOUT", "GROUNDING_FAILURE",
  "EMPTY_REPLY", "HANDOFF_FAILURE", "INTERNAL_ERROR",
];

function ErrorsTab({ data, onDrill }: { data: ErrorsOut; onDrill: (code: string) => void }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;
  return (
    <div className="surface-card overflow-x-auto p-4">
      <p className="mb-2 text-sm text-muted-foreground">Tổng số request: {data.total_requests ?? "N/A"}. Bấm 1 mã lỗi để xem danh sách trace.</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th className="py-1">error_code</th><th>Tỷ lệ</th><th>Số lượng</th><th>Ghi chú</th>
          </tr>
        </thead>
        <tbody>
          {KNOWN_ERROR_CODES_ORDER.map((code) => {
            const m = data.breakdown?.[code];
            return (
              <tr key={code} className="cursor-pointer border-t hover:bg-accent/50" onClick={() => onDrill(code)}>
                <td className="py-1 font-mono text-xs">{code}</td>
                <td>{formatMetric(m, { percent: true })}</td>
                <td>{m?.numerator ?? "N/A"}</td>
                <td className="text-[11px] italic text-muted-foreground">{m?.note ?? ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {data.unrecognized_error_codes && data.unrecognized_error_codes.length > 0 && (
        <p className="mt-2 text-xs text-amber-600">Mã lỗi chưa nằm trong danh sách chuẩn: {data.unrecognized_error_codes.join(", ")}</p>
      )}
    </div>
  );
}

function JudgeTab({ data }: { data: JudgeOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Tổng số đã enqueue" metric={{ value: data.total_judged ?? null, status: "AVAILABLE" }} />
        <MetricCard label="PENDING" metric={{ value: data.judged_pending ?? null, status: "AVAILABLE" }} />
        <MetricCard label="COMPLETED" metric={{ value: data.judged_completed ?? null, status: "AVAILABLE" }} />
        <MetricCard label="FAILED" metric={{ value: data.judged_failed ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Judge Cost (USD)" metric={data.judge_cost_usd} />
        <MetricCard label="Judge input tokens" metric={{ value: data.judge_input_tokens ?? null, status: "AVAILABLE" }} />
        <MetricCard label="Judge output tokens" metric={{ value: data.judge_output_tokens ?? null, status: "AVAILABLE" }} />
      </div>
      {data.disclaimer && <p className="text-xs italic text-muted-foreground">{data.disclaimer}</p>}
      {data.low_score_cases && data.low_score_cases.length > 0 && (
        <div className="surface-card overflow-x-auto p-4">
          <p className="mb-2 text-sm font-medium">Case điểm thấp (&lt; 0.5)</p>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted-foreground"><th>Trace</th><th>Path</th><th>Điểm</th></tr></thead>
            <tbody>
              {data.low_score_cases.map((c) => (
                <tr key={c.judge_id} className="border-t">
                  <td className="py-1"><Link className="text-primary underline" href={`/admin/monitoring/traces/${c.trace_id}`}>{c.trace_id?.slice(0, 8)}</Link></td>
                  <td>{c.execution_path ?? "N/A"}</td>
                  <td>{c.score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function GoldenTab({ data }: { data: GoldenOut }) {
  if (!data.available) return <UnavailableState reason={data.reason} />;
  if (!data.has_run || !data.latest_run) {
    return <div className="surface-card p-4 text-sm text-muted-foreground">Chưa có golden run nào được persist. Chạy `run_golden_evaluation.py --persist` để có dữ liệu.</div>;
  }
  const run = data.latest_run;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard label="Golden set version" metric={{ value: run.golden_set_version, status: "AVAILABLE" }} />
        <MetricCard label="Pass rate" metric={{ value: run.pass_rate, status: run.pass_rate !== null ? "AVAILABLE" : "NOT_APPLICABLE" }} percent />
        <MetricCard label="Regression gate" metric={{ value: run.regression_gate_passed ? "PASS" : "FAIL", status: "AVAILABLE" }} />
        <MetricCard label="Số case" metric={{ value: `${run.passed_cases}/${run.total_cases}`, status: "AVAILABLE" }} />
      </div>
      <div className="surface-card p-4">
        <p className="mb-2 text-sm font-medium">Theo category</p>
        <table className="w-full text-sm">
          <tbody>
            {Object.entries(run.by_category).map(([cat, v]) => (
              <tr key={cat} className="border-t"><td className="py-1">{cat}</td><td>{v.passed}/{v.total}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      {run.failed_case_ids.length > 0 && (
        <div className="surface-card p-4">
          <p className="mb-2 text-sm font-medium text-destructive">Case fail: {run.failed_case_ids.join(", ")}</p>
        </div>
      )}
      <p className="text-xs italic text-muted-foreground">
        Lưu ý: category FALLBACK chưa có case E2E thật (không thể trigger chỉ bằng nội dung tin nhắn, cần fault injection tầng runtime) -- xem BUILD-35 report.
      </p>
    </div>
  );
}

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
          <select className="rounded border bg-background px-2 py-1 text-sm" value={section} onChange={(e) => setSection(e.target.value)}>
            {["overview", "quality", "retrieval", "performance", "cost", "errors", "judge"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Before model</label>
          <input className="rounded border bg-background px-2 py-1 text-sm" value={before.model ?? ""} onChange={(e) => setBefore({ ...before, model: e.target.value || undefined })} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Before prompt_version</label>
          <input className="rounded border bg-background px-2 py-1 text-sm" value={before.promptVersion ?? ""} onChange={(e) => setBefore({ ...before, promptVersion: e.target.value || undefined })} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">After model</label>
          <input className="rounded border bg-background px-2 py-1 text-sm" value={after.model ?? ""} onChange={(e) => setAfter({ ...after, model: e.target.value || undefined })} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">After prompt_version</label>
          <input className="rounded border bg-background px-2 py-1 text-sm" value={after.promptVersion ?? ""} onChange={(e) => setAfter({ ...after, promptVersion: e.target.value || undefined })} />
        </div>
        <button type="button" className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground" onClick={run}>So sánh</button>
      </div>
      {loading && <LoadingState />}
      {error && <ErrorState message={error} />}
      {result && result.available && (
        <pre className="surface-card overflow-x-auto p-4 text-xs">{JSON.stringify(result.comparison, null, 2)}</pre>
      )}
      {result && !result.available && <UnavailableState reason={result.reason} />}
    </div>
  );
}

export default function AdminMonitoringPage() {
  const { accessToken } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [filters, setFilters] = useState<MonitoringFiltersInput>({});
  const [versionOptions, setVersionOptions] = useState<VersionFiltersOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [overview, setOverview] = useState<OverviewOut | null>(null);
  const [quality, setQuality] = useState<QualityOut | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalOut | null>(null);
  const [performance, setPerformance] = useState<PerformanceOut | null>(null);
  const [cost, setCost] = useState<CostOut | null>(null);
  const [errors, setErrors] = useState<ErrorsOut | null>(null);
  const [judge, setJudge] = useState<JudgeOut | null>(null);
  const [golden, setGolden] = useState<GoldenOut | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    getVersionFilters(accessToken).then(setVersionOptions).catch(() => {});
  }, [accessToken]);

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Admin Monitoring Dashboard V2</h1>
        <p className="text-sm text-muted-foreground">Dữ liệu durable từ BUILD-32/33/34/35 -- không đọc ring buffer làm nguồn chính (trừ nơi ghi rõ "ring buffer").</p>
      </div>

      {activeTab !== "safety" && activeTab !== "versions" && activeTab !== "golden" && (
        <FilterBar filters={filters} setFilters={setFilters} options={versionOptions} />
      )}

      <div className="flex flex-wrap gap-1 border-b">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm ${isActive ? "border-primary font-medium text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              <Icon className="h-4 w-4" /> {tab.label}
            </button>
          );
        })}
        <Link href="/admin/monitoring/traces" className="ml-auto flex items-center gap-1.5 px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
          Trace Explorer →
        </Link>
      </div>

      {activeTab === "safety" ? (
        <div className="surface-card p-4 text-sm">
          Dữ liệu Safety & Handoff dùng chung API đã có từ BUILD-34:{" "}
          <a className="text-primary underline" href="/api/v1/admin/safety/summary" target="_blank" rel="noreferrer">
            /admin/safety/summary
          </a>
          . Xem chi tiết từng event tại{" "}
          <a className="text-primary underline" href="/api/v1/admin/safety/events" target="_blank" rel="noreferrer">
            /admin/safety/events
          </a>
          .
        </div>
      ) : activeTab === "versions" ? (
        <VersionsTab accessToken={accessToken} />
      ) : loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error} />
      ) : (
        <>
          {activeTab === "overview" && overview && <OverviewTab data={overview} />}
          {activeTab === "quality" && quality && <QualityTab data={quality} />}
          {activeTab === "retrieval" && retrieval && <RetrievalTab data={retrieval} />}
          {activeTab === "performance" && performance && <PerformanceTab data={performance} />}
          {activeTab === "cost" && cost && <CostTab data={cost} />}
          {activeTab === "errors" && errors && (
            <ErrorsTab data={errors} onDrill={(code) => setFilters({ ...filters, errorCode: code })} />
          )}
          {activeTab === "judge" && judge && <JudgeTab data={judge} />}
          {activeTab === "golden" && golden && <GoldenTab data={golden} />}
        </>
      )}
    </div>
  );
}
