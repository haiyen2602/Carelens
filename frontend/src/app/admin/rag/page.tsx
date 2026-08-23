"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Database,
  FileSearch,
  Filter,
  Layers,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Zap,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { PipelineSwitcher } from "./_pipeline-switcher";

type ActiveTab = "overview" | "retrieval" | "generation" | "safety" | "system" | "traces";
type NumericMetric = number | null;

interface MetricBag {
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
  faithfulness_sample_count?: number;
  answer_relevance_sample_count?: number;
}

interface TrendPoint {
  date: string;
  faithfulness: NumericMetric;
  relevance: NumericMetric;
  latency_p95: number;
  requests: number;
}

interface HealthData {
  status: string;
  kpis: MetricBag;
  trend: TrendPoint[];
}

interface WorstQuery {
  query: string;
  count: number;
  avg_top1: number;
  precision: number;
  recall: number;
  faithfulness: number;
  last_seen: string;
}

interface RetrievalData {
  metrics: MetricBag;
  worst_queries: WorstQuery[];
}

interface GenerationModelBreakdown {
  model: string;
  requests: number;
  faithfulness: NumericMetric;
}

interface GenerationData {
  metrics: MetricBag;
  breakdown_by_model: GenerationModelBreakdown[];
}

interface SafetyIncident {
  id: string;
  severity: string;
  reason?: string;
  failure_type?: string;
  status: string;
}

interface SafetyData {
  critical_safety_failures?: number;
  dosage_consistency_failures?: number;
  interaction_unsupported_claims?: number;
  incidents: SafetyIncident[];
}

interface LatencyStep {
  component: string;
  duration_ms: number;
}

interface SystemData {
  latency_waterfall: LatencyStep[];
}

interface TraceSummary {
  trace_id: string;
  timestamp: string;
  query_preview: string;
  final_answer: string;
  latency_ms: number;
  faithfulness: NumericMetric;
  relevance: NumericMetric;
  status: string;
  model: string;
}

interface FilterOptions {
  chatbot_versions: { value: string; label: string }[];
  models: string[];
  prompt_versions: string[];
  environments: string[];
}

async function readJson<T>(response: Response): Promise<T | null> {
  return response.ok ? (response.json() as Promise<T>) : null;
}

export default function RagDashboardPage() {
  const { accessToken } = useAuth();
  const [activeTab, setActiveTab] = useState<ActiveTab>("overview");
  const [healthData, setHealthData] = useState<HealthData | null>(null);
  const [retrievalData, setRetrievalData] = useState<RetrievalData | null>(null);
  const [systemData, setSystemData] = useState<SystemData | null>(null);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  // BUILD-25B: Filters -- these now genuinely filter the data fetched below
  // (query params sent to the backend, which applies them to the real trace
  // list before computing any metric -- see backend/api/rag_monitoring_routes.py
  // `_filter_traces`), not just cosmetic <select> state. Default view is
  // "agent-v2" (production's real chatbot), not a mix of both systems --
  // pick "Tất cả" or "Legacy Chatbot" explicitly to see legacy traffic.
  const [chatbotVersionFilter, setChatbotVersionFilter] = useState("agent-v2");
  const [modelFilter, setModelFilter] = useState("all");
  const [promptFilter, setPromptFilter] = useState("all");
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    chatbot_versions: [],
    models: [],
    prompt_versions: [],
    environments: [],
  });

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const [generationData, setGenerationData] = useState<GenerationData | null>(null);
  const [safetyData, setSafetyData] = useState<SafetyData | null>(null);

  const fetchDashboardData = useCallback(
    async (isBackground = false) => {
      if (!accessToken) return;
      if (!isBackground) setLoading(true);
      try {
        const headers: Record<string, string> = { Authorization: `Bearer ${accessToken}` };
        // Real filter params, applied by the backend to the same trace list
        // every metric below is computed from -- changing these dropdowns
        // actually changes what's fetched, not just what's displayed.
        const qs = new URLSearchParams();
        if (chatbotVersionFilter !== "all") qs.set("chatbot_version", chatbotVersionFilter);
        if (modelFilter !== "all") qs.set("model", modelFilter);
        if (promptFilter !== "all") qs.set("prompt_version", promptFilter);
        const q = qs.toString() ? `?${qs.toString()}` : "";

        const [
          healthRes,
          retrievalRes,
          generationRes,
          safetyRes,
          systemRes,
          tracesRes,
          filtersRes,
        ] = await Promise.all([
          fetch(`${apiBase}/api/v1/admin/rag/health${q}`, { headers })
            .then(readJson<HealthData>)
            .catch(() => null),
          fetch(`${apiBase}/api/v1/admin/rag/retrieval${q}`, { headers })
            .then(readJson<RetrievalData>)
            .catch(() => null),
          fetch(`${apiBase}/api/v1/admin/rag/generation${q}`, { headers })
            .then(readJson<GenerationData>)
            .catch(() => null),
          fetch(`${apiBase}/api/v1/admin/rag/safety${q}`, { headers })
            .then(readJson<SafetyData>)
            .catch(() => null),
          fetch(`${apiBase}/api/v1/admin/rag/system${q}`, { headers })
            .then(readJson<SystemData>)
            .catch(() => null),
          fetch(`${apiBase}/api/v1/admin/rag/traces${q}`, { headers })
            .then(async (response) => (await readJson<TraceSummary[]>(response)) ?? [])
            .catch(() => []),
          // Real, currently-available filter option lists -- built from
          // actual trace metadata, not a hardcoded <option> list.
          fetch(`${apiBase}/api/v1/admin/rag/filters`, { headers })
            .then(readJson<FilterOptions>)
            .catch(() => null),
        ]);

        if (healthRes) setHealthData(healthRes);
        if (retrievalRes) setRetrievalData(retrievalRes);
        if (generationRes) setGenerationData(generationRes);
        if (safetyRes) setSafetyData(safetyRes);
        if (systemRes) setSystemData(systemRes);
        if (Array.isArray(tracesRes)) setTraces(tracesRes);
        if (filtersRes) setFilterOptions(filtersRes);
        setLastUpdated(new Date());
      } catch (e) {
        console.error("Failed to load RAG monitoring data:", e);
      } finally {
        if (!isBackground) setLoading(false);
      }
    },
    [accessToken, apiBase, chatbotVersionFilter, modelFilter, promptFilter],
  );

  useEffect(() => {
    if (!accessToken) return;
    fetchDashboardData();
    // Automatic live polling every 10 seconds without needing manual toggle
    const interval = setInterval(() => {
      fetchDashboardData(true);
    }, 10000);
    return () => clearInterval(interval);
    // Re-fetch (not just re-render) whenever a filter changes, since the
    // filter values are sent to the backend as real query params.
  }, [accessToken, fetchDashboardData]);

  const kpis = healthData?.kpis || {
    faithfulness: 0,
    answer_relevance: 0,
    p95_latency_ms: 0,
    critical_safety_failure_rate: 0,
  };

  const safePct = (val: NumericMetric | undefined) => {
    const num = Number(val);
    if (isNaN(num)) return 0;
    return num <= 1.0 ? Math.round(num * 100) : Math.round(num);
  };
  const metricPct = (val: NumericMetric | undefined) =>
    typeof val === "number" ? `${safePct(val)}%` : "N/A";

  const trend = healthData?.trend || [];
  const worstQueries = retrievalData?.worst_queries || [];

  return (
    <div className="space-y-6">
      <PipelineSwitcher active="chatbot" />
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">Giám sát & Đánh giá RAG Chatbot</h1>
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
              Langfuse Observability
            </span>
            <span className="flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
              Live Real-time (10s)
            </span>
          </div>
          {/* BUILD-25B: explicit, unambiguous chatbot-identity + environment
              badge -- which system's data this view is showing, and where it
              actually came from, right next to the title. */}
          <div className="flex flex-wrap items-center gap-2 mt-1.5">
            <span className="rounded-full bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-700">
              Chatbot Version:{" "}
              {chatbotVersionFilter === "agent-v2"
                ? "Agent V2 / Production"
                : chatbotVersionFilter === "legacy"
                  ? "Legacy Chatbot"
                  : "Tất cả hệ thống"}
            </span>
            {filterOptions.environments[0] && (
              <span className="rounded-full bg-slate-50 border border-slate-200 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700">
                Environment: {filterOptions.environments[0]}
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Dữ liệu thật 100% từ Database và Langfuse Telemetry Traces (Tự động đồng bộ liên tục).
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchDashboardData(false)}
            className="flex items-center gap-1.5"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Làm mới ngay
          </Button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="surface-card flex flex-wrap items-center gap-3 p-3 text-sm">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mr-1">
          <Filter className="h-3.5 w-3.5 text-primary" />
          Bộ lọc:
        </div>
        {/* BUILD-25B: every option below comes from GET /admin/rag/filters --
            real trace metadata (or, only when no trace exists yet, the
            currently-configured model/version for each known system) --
            never a hardcoded legacy-only list. Changing any of these three
            actually re-fetches every tab's data filtered by that value (see
            fetchDashboardData's query string above), not just this label. */}
        <select
          value={chatbotVersionFilter}
          onChange={(e) => setChatbotVersionFilter(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2.5 text-xs font-medium"
        >
          <option value="all">Chatbot Version: Tất cả</option>
          {filterOptions.chatbot_versions.map((v) => (
            <option key={v.value} value={v.value}>
              Chatbot Version: {v.label}
            </option>
          ))}
        </select>
        <select
          value={modelFilter}
          onChange={(e) => setModelFilter(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2.5 text-xs font-medium"
        >
          <option value="all">Model: Tất cả</option>
          {filterOptions.models.map((m) => (
            <option key={m} value={m}>
              Model: {m}
            </option>
          ))}
        </select>
        <select
          value={promptFilter}
          onChange={(e) => setPromptFilter(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2.5 text-xs font-medium"
        >
          <option value="all">Prompt/Runtime Version: Tất cả</option>
          {filterOptions.prompt_versions.map((p) => (
            <option key={p} value={p}>
              Prompt/Runtime Version: {p}
            </option>
          ))}
        </select>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
          <span className="text-muted-foreground">Trạng thái RAG:</span>
          <span className="font-semibold text-emerald-600">{healthData?.status || "Live"}</span>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-border gap-2 overflow-x-auto text-sm font-medium">
        {[
          { id: "overview", label: "Tổng quan & Health", icon: Activity },
          { id: "retrieval", label: "Retrieval Quality", icon: Database },
          { id: "generation", label: "Generation & Faithfulness", icon: Sparkles },
          { id: "safety", label: "An toàn & Sự cố Thuốc", icon: ShieldAlert },
          { id: "system", label: "Độ trễ & Pipeline", icon: Zap },
          { id: "traces", label: "Trace Explorer", icon: FileSearch },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as ActiveTab)}
              className={`flex items-center gap-2 px-4 py-2.5 transition border-b-2 font-semibold whitespace-nowrap ${
                isActive
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab: Overview */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* KPI Cards */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="surface-card p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground uppercase">
                  Faithfulness
                </span>
                <span className="rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 text-[11px] font-semibold">
                  Mục tiêu &ge; 85%
                </span>
              </div>
              <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">
                {metricPct(kpis.faithfulness)}
              </p>
              <p className="mt-2 text-xs font-semibold text-muted-foreground">
                Độ trung thực tính theo trace thật
              </p>
            </div>

            <div className="surface-card p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground uppercase">
                  Answer Relevance
                </span>
                <span className="rounded-full bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 text-[11px] font-semibold">
                  Mục tiêu &ge; 80%
                </span>
              </div>
              <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">
                {metricPct(kpis.answer_relevance)}
              </p>
              <p className="mt-2 text-xs font-semibold text-primary">
                Khớp ý định & giải quyết câu hỏi
              </p>
            </div>

            <div className="surface-card p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground uppercase">
                  P95 Latency
                </span>
                <span className="rounded-full bg-muted text-muted-foreground px-2 py-0.5 text-[11px] font-semibold">
                  End-to-End
                </span>
              </div>
              <p className="mt-3 text-3xl font-extrabold leading-none text-foreground">
                {kpis.p95_latency_ms || 0}{" "}
                <span className="text-sm font-normal text-muted-foreground">ms</span>
              </p>
              <p className="mt-2 text-xs text-muted-foreground">Độ trễ thực tế từ trace logs</p>
            </div>

            <div className="surface-card p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground uppercase">
                  Sự cố An toàn (High)
                </span>
                <span className="rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 text-[11px] font-semibold">
                  Critical Gate
                </span>
              </div>
              <p className="mt-3 text-3xl font-extrabold leading-none text-emerald-600">
                {safetyData?.critical_safety_failures ?? 0}{" "}
                <span className="text-sm font-normal text-muted-foreground">sự cố</span>
              </p>
              <p className="mt-2 text-xs font-semibold text-emerald-600 flex items-center gap-1">
                <CheckCircle2 className="h-3.5 w-3.5" /> 100% Deterministic Safety Gate
              </p>
            </div>
          </div>

          {/* Chart Section */}
          <div className="surface-card p-5">
            <h2 className="text-base font-bold text-foreground mb-4 flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              Xu hướng Chất lượng RAG (7 ngày qua)
            </h2>
            {trend.length === 0 || trend.every((t) => t.requests === 0) ? (
              <div className="py-12 text-center text-sm text-muted-foreground">
                Chưa có dữ liệu trace trong 7 ngày qua. Hãy thực hiện trò chuyện để ghi nhận dữ liệu
                thật.
              </div>
            ) : (
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trend}>
                    <defs>
                      <linearGradient id="colorFaith" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="colorRel" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#2563eb" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis dataKey="date" stroke="var(--muted-foreground)" fontSize={12} />
                    <YAxis
                      domain={[0.0, 1.0]}
                      stroke="var(--muted-foreground)"
                      fontSize={12}
                      tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#ffffff",
                        borderColor: "var(--border)",
                        borderRadius: "8px",
                        boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                        fontSize: "12px",
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="faithfulness"
                      stroke="#10b981"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#colorFaith)"
                      name="Faithfulness"
                    />
                    <Area
                      type="monotone"
                      dataKey="relevance"
                      stroke="#2563eb"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#colorRel)"
                      name="Answer Relevance"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab: Retrieval */}
      {activeTab === "retrieval" && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="surface-card p-5">
              <span className="text-xs font-semibold text-muted-foreground uppercase">
                HitRate@10
              </span>
              <p className="mt-2 text-3xl font-extrabold text-primary">
                {typeof retrievalData?.metrics?.hit_rate_10 === "number"
                  ? `${(retrievalData.metrics.hit_rate_10 * 100).toFixed(1)}%`
                  : "N/A"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Độ phủ tài liệu liên quan trong top 10
              </p>
            </div>
            <div className="surface-card p-5">
              <span className="text-xs font-semibold text-muted-foreground uppercase">MRR@10</span>
              <p className="mt-2 text-3xl font-extrabold text-primary">
                {typeof retrievalData?.metrics?.mrr_10 === "number"
                  ? retrievalData.metrics.mrr_10.toFixed(2)
                  : "N/A"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Mean Reciprocal Rank của nguồn đúng
              </p>
            </div>

            <div className="surface-card p-5">
              <span className="text-xs font-semibold text-muted-foreground uppercase">NDCG@10</span>
              <p className="mt-2 text-3xl font-extrabold text-primary">
                {typeof retrievalData?.metrics?.ndcg_10 === "number"
                  ? retrievalData.metrics.ndcg_10.toFixed(2)
                  : "N/A"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Golden evaluation với relevance ground truth
              </p>
            </div>
            <div className="surface-card p-5">
              <span className="text-xs font-semibold text-muted-foreground uppercase">
                Tổng số Chunks trong KB
              </span>
              <p className="mt-2 text-3xl font-extrabold text-foreground">
                {retrievalData?.metrics?.total_indexed_chunks ?? 0}
              </p>
              <p className="mt-1 text-xs font-semibold text-emerald-600">
                pgvector HNSW (ef_search=100) · evaluated:{" "}
                {retrievalData?.metrics?.evaluated_sample_count ?? 0}
              </p>
            </div>
          </div>

          {/* Worst queries */}
          <div className="surface-card p-5 space-y-4">
            <h3 className="text-base font-bold text-foreground flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Câu hỏi có độ tin cậy Retrieval thấp (Worst Queries từ thực tế)
            </h3>
            {worstQueries.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                Chưa ghi nhận câu hỏi nào có độ tin cậy thấp hoặc gặp lỗi retrieval.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/50 text-xs font-semibold text-muted-foreground">
                      <th className="py-2.5 px-3">Câu truy vấn</th>
                      <th className="py-2.5 px-3">Lượt hỏi</th>
                      <th className="py-2.5 px-3">Top-1 Score</th>
                      <th className="py-2.5 px-3">Precision</th>
                      <th className="py-2.5 px-3">Recall</th>
                      <th className="py-2.5 px-3">Faithfulness</th>
                      <th className="py-2.5 px-3">Lần cuối</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {worstQueries.map((q, idx) => (
                      <tr key={idx} className="hover:bg-muted/30">
                        <td className="py-2.5 px-3 font-medium text-foreground">{q.query}</td>
                        <td className="py-2.5 px-3 text-muted-foreground">{q.count}</td>
                        <td className="py-2.5 px-3 font-semibold text-amber-600">{q.avg_top1}</td>
                        <td className="py-2.5 px-3">{q.precision}</td>
                        <td className="py-2.5 px-3">{q.recall}</td>
                        <td className="py-2.5 px-3 font-semibold text-primary">{q.faithfulness}</td>
                        <td className="py-2.5 px-3 text-muted-foreground text-xs">{q.last_seen}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab: Traces */}
      {activeTab === "traces" && (
        <div className="surface-card overflow-hidden shadow-sm">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <h3 className="font-bold text-foreground">
              Nhật ký Trace thực tế (Langfuse & Database Traces)
            </h3>
            <span className="text-xs text-muted-foreground">{traces.length} trace records</span>
          </div>
          {traces.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              Chưa có trace nào được ghi nhận. Các trace mới từ bệnh nhân sẽ tự động xuất hiện tại
              đây.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50 text-xs font-semibold text-muted-foreground">
                    <th className="py-3 px-4">Trace ID</th>
                    <th className="py-3 px-4">Thời gian</th>
                    <th className="py-3 px-4">Câu hỏi bệnh nhân</th>
                    <th className="py-3 px-4">Độ trễ</th>
                    <th className="py-3 px-4">Faithfulness</th>
                    <th className="py-3 px-4">Relevance</th>
                    <th className="py-3 px-4">Trạng thái</th>
                    <th className="py-3 px-4 text-right">Thao tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {traces.map((t, idx) => (
                    <tr key={idx} className="hover:bg-muted/30">
                      <td className="py-3 px-4 font-mono text-xs text-primary font-semibold">
                        {t.trace_id}
                      </td>
                      <td className="py-3 px-4 text-xs text-muted-foreground">
                        {new Date(t.timestamp).toLocaleTimeString("vi-VN", {
                          timeZone: "Asia/Ho_Chi_Minh",
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </td>
                      <td className="py-3 px-4 font-medium text-foreground max-w-xs truncate">
                        {t.query_preview}
                      </td>
                      <td className="py-3 px-4 text-muted-foreground">{t.latency_ms} ms</td>
                      <td className="py-3 px-4 font-semibold text-emerald-600">{t.faithfulness}</td>
                      <td className="py-3 px-4 font-semibold text-primary">{t.relevance}</td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                            t.status === "success"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : "bg-rose-50 text-rose-700 border border-rose-200"
                          }`}
                        >
                          {t.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            alert(
                              `Trace ID: ${t.trace_id}\n\nCâu hỏi: ${t.query_preview}\n\nPhản hồi: ${t.final_answer}\n\nModel: ${t.model}`,
                            )
                          }
                        >
                          Chi tiết
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab: Safety */}
      {activeTab === "safety" && (
        <div className="surface-card p-5 space-y-4">
          <h3 className="text-base font-bold text-foreground flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-rose-500" />
            Giám sát An toàn Y tế & Tuân thủ Liều dùng (§10)
          </h3>
          <p className="text-sm text-muted-foreground">
            Số liệu thống kê trực tiếp từ bảng Escalation và Safety Evaluator trong Database.
          </p>
          <div className="grid gap-4 sm:grid-cols-3 pt-2">
            <div className="surface-card p-4 bg-muted/30">
              <span className="text-xs text-muted-foreground font-semibold uppercase">
                Lỗi Liều lượng / Tần suất
              </span>
              <p className="mt-1 text-2xl font-bold text-emerald-600">
                {safetyData?.dosage_consistency_failures ?? 0} vi phạm
              </p>
            </div>
            <div className="surface-card p-4 bg-muted/30">
              <span className="text-xs text-muted-foreground font-semibold uppercase">
                Tương tác thuốc nguy hiểm
              </span>
              <p className="mt-1 text-2xl font-bold text-emerald-600">
                {safetyData?.interaction_unsupported_claims ?? 0} ca
              </p>
            </div>
            <div className="surface-card p-4 bg-muted/30">
              <span className="text-xs text-muted-foreground font-semibold uppercase">
                Tổng số Escalation trong DB
              </span>
              <p className="mt-1 text-2xl font-bold text-foreground">
                {(safetyData?.incidents || []).length} ca
              </p>
            </div>
          </div>

          {safetyData?.incidents && safetyData.incidents.length > 0 && (
            <div className="pt-4">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase mb-2">
                Danh sách sự cố / cảnh báo
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/50 text-xs text-muted-foreground">
                      <th className="py-2 px-3">ID</th>
                      <th className="py-2 px-3">Mức độ</th>
                      <th className="py-2 px-3">Lý do</th>
                      <th className="py-2 px-3">Trạng thái</th>
                    </tr>
                  </thead>
                  <tbody>
                    {safetyData.incidents.map((inc, i) => (
                      <tr key={i} className="border-b border-border">
                        <td className="py-2 px-3 font-mono text-xs">{inc.id.slice(0, 8)}</td>
                        <td className="py-2 px-3 font-semibold uppercase text-xs">
                          {inc.severity}
                        </td>
                        <td className="py-2 px-3">{inc.reason || inc.failure_type}</td>
                        <td className="py-2 px-3 text-xs">{inc.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab: Generation */}
      {activeTab === "generation" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="surface-card p-5 space-y-3">
            <h3 className="font-bold text-foreground flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" /> Đánh giá Chất lượng Generation (Thực tế)
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between py-2 border-b border-border">
                <span className="text-muted-foreground">Faithfulness (Độ trung thực):</span>
                <span className="font-bold text-emerald-600">
                  {metricPct(generationData?.metrics?.faithfulness)}
                </span>
              </div>
              <div className="flex justify-between py-2 border-b border-border">
                <span className="text-muted-foreground">Answer Relevance (Độ phù hợp):</span>
                <span className="font-bold text-primary">
                  {metricPct(generationData?.metrics?.answer_relevance)}
                </span>
              </div>
              <div className="flex justify-between py-2 border-b border-border">
                <span className="text-muted-foreground">Tỷ lệ Hallucination (Ảo giác):</span>
                <span className="font-bold text-emerald-600">
                  {metricPct(generationData?.metrics?.hallucination_rate)}
                </span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-muted-foreground">Độ chính xác từ chối (Abstention):</span>
                <span className="font-bold text-foreground">
                  {metricPct(generationData?.metrics?.abstention_accuracy)}
                </span>
              </div>
            </div>
          </div>

          <div className="surface-card p-5 space-y-3">
            <h3 className="font-bold text-foreground">Phân bổ theo Prompt & Model</h3>
            <div className="space-y-2 text-sm">
              {(generationData?.breakdown_by_model || []).map((m, idx) => (
                <div key={idx} className="p-3 bg-muted/40 rounded-lg space-y-1">
                  <div className="flex justify-between font-semibold">
                    <span>Model: {m.model}</span>
                    <span className="text-emerald-600">Lượt gọi: {m.requests}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Faithfulness trung bình: {safePct(m.faithfulness)}%
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab: System */}
      {activeTab === "system" && (
        <div className="surface-card p-5 space-y-4">
          <h3 className="text-base font-bold text-foreground flex items-center gap-2">
            <Zap className="h-4 w-4 text-primary" />
            Phân rã độ trễ từng bước Pipeline (Thực tế từ Traces)
          </h3>
          {!systemData?.latency_waterfall || systemData.latency_waterfall.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              Chưa có dữ liệu span chi tiết trong trace buffer. Hãy thực hiện trò chuyện để ghi nhận
              độ trễ từng bước.
            </div>
          ) : (
            <div className="space-y-3">
              {(() => {
                const maxDuration = Math.max(
                  ...systemData.latency_waterfall.map((s) => s.duration_ms || 0),
                  1,
                );
                return systemData.latency_waterfall.map((step, idx) => {
                  const pct = Math.max(2, Math.round((step.duration_ms / maxDuration) * 100));
                  return (
                    <div key={idx} className="space-y-1">
                      <div className="flex justify-between text-xs font-semibold text-foreground">
                        <span className="font-mono">{step.component}</span>
                        <span className="text-muted-foreground">{step.duration_ms} ms</span>
                      </div>
                      <div className="w-full bg-muted h-2.5 rounded-full overflow-hidden">
                        <div
                          className="bg-primary h-full rounded-full transition-all duration-300"
                          style={{ width: `${pct}%` }}
                        ></div>
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
