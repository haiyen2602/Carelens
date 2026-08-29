// BUILD-36: Admin Monitoring Dashboard V2 -- calls the backend directly
// with a Bearer token (same pattern as frontend/src/lib/feedback-tickets.ts
// and app/admin/rag/page.tsx), not through a Next.js proxy route.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function authHeaders(accessToken?: string | null): HeadersInit | undefined {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined;
}

async function parseOrThrow<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `${fallback} (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

// A rate/metric value from the backend is ALWAYS this shape (backend.
// services.agent_monitoring_metrics._rate/_average/_percentiles) -- never a
// bare number. `value: null` MUST render as the literal text "N/A", never
// "0%"/"0.00" (spec §18).
export type MetricValue = {
  value: number | string | null;
  numerator?: number | null;
  denominator?: number | null;
  sample_count?: number | null;
  status: "AVAILABLE" | "NOT_APPLICABLE" | "NOT_AVAILABLE";
  reason?: string;
  scope?: string;
  note?: string;
  scope_note?: string;
  metric_type?: "LIVE" | "GOLDEN" | "HEURISTIC" | "LLM_JUDGE" | "DETERMINISTIC";
};

export type MonitoringFiltersInput = {
  dateFrom?: string;
  dateTo?: string;
  model?: string;
  promptVersion?: string;
  retrievalVersion?: string;
  evaluationVersion?: string;
  executionPath?: string;
  status?: string;
  errorCode?: string;
  safetySeverity?: string;
  judgeModel?: string;
  rubricVersion?: string;
  judgeScoreMin?: number;
  judgeScoreMax?: number;
};

function filtersToParams(filters: MonitoringFiltersInput): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.model && filters.model !== "all") params.set("model", filters.model);
  if (filters.promptVersion && filters.promptVersion !== "all") params.set("prompt_version", filters.promptVersion);
  if (filters.retrievalVersion && filters.retrievalVersion !== "all") params.set("retrieval_version", filters.retrievalVersion);
  if (filters.evaluationVersion && filters.evaluationVersion !== "all") params.set("evaluation_version", filters.evaluationVersion);
  if (filters.executionPath && filters.executionPath !== "all") params.set("execution_path", filters.executionPath);
  if (filters.status && filters.status !== "all") params.set("status", filters.status);
  if (filters.errorCode && filters.errorCode !== "all") params.set("error_code", filters.errorCode);
  if (filters.safetySeverity && filters.safetySeverity !== "all") params.set("safety_severity", filters.safetySeverity);
  if (filters.judgeModel && filters.judgeModel !== "all") params.set("judge_model", filters.judgeModel);
  if (filters.rubricVersion && filters.rubricVersion !== "all") params.set("rubric_version", filters.rubricVersion);
  if (filters.judgeScoreMin !== undefined) params.set("judge_score_min", String(filters.judgeScoreMin));
  if (filters.judgeScoreMax !== undefined) params.set("judge_score_max", String(filters.judgeScoreMax));
  return params;
}

async function getSection<T>(
  section: string,
  filters: MonitoringFiltersInput,
  accessToken: string | null | undefined,
  signal?: AbortSignal,
): Promise<T> {
  const params = filtersToParams(filters);
  const response = await fetch(`${API_BASE}/api/v1/admin/monitoring/${section}?${params}`, {
    headers: authHeaders(accessToken),
    signal,
  });
  return parseOrThrow(response, `Không thể tải dữ liệu ${section}`);
}

export type OverviewOut = {
  available: boolean;
  reason?: string;
  total_requests?: number;
  success_rate?: MetricValue;
  fallback_rate?: MetricValue;
  error_rate?: MetricValue;
  timeout_rate?: MetricValue;
  empty_reply_rate?: MetricValue;
  latency_p50_ms?: MetricValue;
  latency_p95_ms?: MetricValue;
  tokens_per_query?: MetricValue;
  cost_per_query_usd?: MetricValue;
  daily_cost_usd?: MetricValue;
  ticket_rate?: MetricValue;
  safety_trigger_rate?: MetricValue;
  handoff_rate?: MetricValue;
  judged_rate?: MetricValue;
};

export type QualityOut = {
  available: boolean;
  reason?: string;
  rag_faithfulness?: MetricValue;
  rag_answer_relevance?: MetricValue;
  golden_hit_rate_at_10?: MetricValue;
  golden_mrr_at_10?: MetricValue;
  golden_ndcg_at_10?: MetricValue;
  judge_overall_score?: MetricValue;
  golden_pass_rate?: MetricValue & { run_id?: string | null };
  regression_gate_status?: MetricValue & { run_id?: string | null };
};

export type RetrievalOut = {
  available: boolean;
  reason?: string;
  rag_query_volume?: number;
  retrieval_latency_p50_ms?: MetricValue;
  retrieval_latency_p95_ms?: MetricValue;
  empty_retrieval_rate?: MetricValue;
  grounding_failure_rate?: MetricValue;
  citation_count_scope?: string;
  golden_hit_rate_at_10?: MetricValue;
  golden_mrr_at_10?: MetricValue;
  golden_ndcg_at_10?: MetricValue;
  golden_precision_at_10?: MetricValue;
};

export type PerformanceOut = {
  available: boolean;
  reason?: string;
  end_to_end_p50_ms?: MetricValue;
  end_to_end_p95_ms?: MetricValue;
  end_to_end_p99_ms?: MetricValue;
  per_step?: Record<string, { 50: MetricValue; 95: MetricValue }>;
  timeout_rate?: MetricValue;
};

export type CostOut = {
  available: boolean;
  reason?: string;
  agent_cost_usd?: MetricValue;
  judge_cost_usd?: MetricValue;
  total_cost_usd?: MetricValue;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  tokens_per_query?: MetricValue;
  cost_per_query_usd?: MetricValue;
  by_model_usd?: Record<string, number>;
  timeline?: Array<{ timestamp: string; [model: string]: number | string }>;
  models?: string[];
};

export type ErrorsOut = {
  available: boolean;
  reason?: string;
  total_requests?: number;
  breakdown?: Record<string, MetricValue>;
  unrecognized_error_codes?: string[];
};

export type JudgeOut = {
  available: boolean;
  reason?: string;
  total_judged?: number;
  judged_pending?: number;
  judged_completed?: number;
  judged_failed?: number;
  provider_model_distribution?: Record<string, number>;
  overall_score_distribution?: Record<string, number>;
  low_score_cases?: { judge_id: string; agent_run_id: string; trace_id: string; score: number; execution_path: string | null }[];
  judge_cost_usd?: MetricValue;
  judge_input_tokens?: number;
  judge_output_tokens?: number;
  disclaimer?: string;
};

export type GoldenRunSummary = {
  run_id: string;
  golden_set_version: string;
  created_at: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  pass_rate: number | null;
  regression_gate_passed: boolean;
  regression_gate: Record<string, unknown>;
  provenance: Record<string, unknown>;
  comparisons: { case_id: string; category: string; status: string; baseline_passed: boolean | null; candidate_passed: boolean }[];
  by_category: Record<string, { total: number; passed: number }>;
  failed_case_ids: string[];
};

export type GoldenOut = {
  available: boolean;
  reason?: string;
  has_run?: boolean;
  latest_run?: GoldenRunSummary;
  history?: { run_id: string; golden_set_version: string; created_at: string; pass_rate: number | null; regression_gate_passed: boolean }[];
};

export type GoldenRunDetail = GoldenRunSummary & {
  aggregate: Record<string, unknown>;
  git_commit: string;
  started_at: string;
  completed_at: string | null;
  cases: { case_id: string; category: string; passed: boolean; checks: { name: string; status: string; detail: string }[] }[];
};

export type VersionFiltersOut = {
  available: boolean;
  reason?: string;
  model?: string[];
  prompt_version?: string[];
  retrieval_version?: string[];
  evaluation_version?: string[];
  execution_path?: string[];
  status?: string[];
  error_code?: string[];
  judge_model?: string[];
  rubric_version?: string[];
  safety_severity?: string[];
  golden_set_version?: string[];
};

export type TraceListItem = {
  agent_run_id: string;
  trace_id: string | null;
  conversation_id: string | null;
  patient_id: string | null;
  intent: string | null;
  status: string;
  execution_path: string | null;
  model: string | null;
  started_at: string | null;
  duration_ms: number | null;
  error_code: string | null;
  timeout: boolean;
  total_cost_usd: number | null;
  cost_status: string;
  has_ticket: boolean;
  has_safety_event: boolean;
  has_judge_result: boolean;
};

export type TraceListOut = {
  available: boolean;
  reason?: string;
  items: TraceListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type TraceDetailOut = {
  trace_id: string | null;
  agent_run_id: string;
  conversation_id: string | null;
  patient_id: string | null;
  execution_path: string | null;
  intent: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  model: string | null;
  model_calls: number;
  prompt_version: string | null;
  retrieval_version: string | null;
  spans: { span_name: string; span_type: string; status: string; duration_ms: number; started_at: string; metadata: Record<string, unknown> }[];
  tokens: { input: number; cached_input: number; output: number; total: number };
  cost: { input_usd: number | null; output_usd: number | null; total_usd: number | null; status: string };
  error_code: string | null;
  timeout: boolean;
  empty_reply: boolean;
  evaluation: Record<string, unknown> | null;
  judge: { judge_status: string; overall_score: number | null; dimension_scores: Record<string, number>; flags: string[]; judge_model: string; rubric_version: string; eligibility_reason: string } | null;
  safety: { outcome: string; reason_code: string; severity: string; handoff_required: boolean; handoff_created: boolean; handoff_id: string | null } | null;
  ticket: { ticket_id: string; status: string; reason: string } | null;
  content_available: boolean;
  query_preview: string | null;
  response_preview: string | null;
  tool_names: string[];
  citations: unknown;
};

export type SessionDetailOut = {
  available: boolean;
  items: unknown[];
  total: number;
  limit: number;
  offset: number;
};

export type CompareOut = {
  available: boolean;
  reason?: string;
  section?: string;
  comparison?: Record<string, unknown>;
};

export type TrendPoint = {
  date: string;
  requests: number;
  p95_latency_ms: number | null;
  faithfulness: number | null;
  faithfulness_n: number;
  relevance: number | null;
  relevance_n: number;
};

export type TrendOut = {
  available: boolean;
  reason?: string;
  trend: TrendPoint[];
  days: number;
};

export async function getOverview(filters: MonitoringFiltersInput, accessToken?: string | null, signal?: AbortSignal) {
  return getSection<OverviewOut>("overview", filters, accessToken, signal);
}
export async function getQuality(filters: MonitoringFiltersInput, accessToken?: string | null, signal?: AbortSignal) {
  return getSection<QualityOut>("quality", filters, accessToken, signal);
}
export async function getRetrieval(filters: MonitoringFiltersInput, accessToken?: string | null, signal?: AbortSignal) {
  return getSection<RetrievalOut>("retrieval", filters, accessToken, signal);
}
export async function getPerformance(filters: MonitoringFiltersInput, accessToken?: string | null, signal?: AbortSignal) {
  return getSection<PerformanceOut>("performance", filters, accessToken, signal);
}
export async function getCost(filters: MonitoringFiltersInput, accessToken?: string | null, signal?: AbortSignal) {
  return getSection<CostOut>("cost", filters, accessToken, signal);
}
export async function getErrors(filters: MonitoringFiltersInput, accessToken?: string | null, signal?: AbortSignal) {
  return getSection<ErrorsOut>("errors", filters, accessToken, signal);
}
export async function getJudge(filters: MonitoringFiltersInput, accessToken?: string | null, signal?: AbortSignal) {
  return getSection<JudgeOut>("judge", filters, accessToken, signal);
}

export async function getTrend(
  filters: MonitoringFiltersInput,
  days: number = 7,
  accessToken?: string | null,
  signal?: AbortSignal,
): Promise<TrendOut> {
  const params = filtersToParams(filters);
  params.set("days", String(days));
  const response = await fetch(`${API_BASE}/api/v1/admin/monitoring/trend?${params}`, {
    headers: authHeaders(accessToken),
    signal,
  });
  return parseOrThrow<TrendOut>(response, "Không thể tải dữ liệu trend");
}

export async function getGolden(goldenSetVersion: string | undefined, accessToken?: string | null): Promise<GoldenOut> {
  const params = new URLSearchParams();
  if (goldenSetVersion && goldenSetVersion !== "all") params.set("golden_set_version", goldenSetVersion);
  const response = await fetch(`${API_BASE}/api/v1/admin/monitoring/golden?${params}`, { headers: authHeaders(accessToken) });
  return parseOrThrow(response, "Không thể tải dữ liệu Golden Evaluation");
}

export async function getGoldenRun(runId: string, accessToken?: string | null): Promise<GoldenRunDetail> {
  const response = await fetch(`${API_BASE}/api/v1/admin/monitoring/golden/${encodeURIComponent(runId)}`, { headers: authHeaders(accessToken) });
  return parseOrThrow(response, "Không thể tải chi tiết golden run");
}

export async function getVersionFilters(accessToken?: string | null): Promise<VersionFiltersOut> {
  const response = await fetch(`${API_BASE}/api/v1/admin/monitoring/versions/filters`, { headers: authHeaders(accessToken) });
  return parseOrThrow(response, "Không thể tải danh sách filter version");
}

export async function compareVersions(
  section: string,
  before: MonitoringFiltersInput,
  after: MonitoringFiltersInput,
  accessToken?: string | null,
): Promise<CompareOut> {
  const params = new URLSearchParams({ section });
  const beforeP = filtersToParams(before);
  const afterP = filtersToParams(after);
  for (const [k, v] of beforeP) params.set(`before_${k}`, v);
  for (const [k, v] of afterP) params.set(`after_${k}`, v);
  const response = await fetch(`${API_BASE}/api/v1/admin/monitoring/versions/compare?${params}`, { headers: authHeaders(accessToken) });
  return parseOrThrow(response, "Không thể so sánh version");
}

export async function listTraces(
  filters: MonitoringFiltersInput,
  options: { limit?: number; offset?: number; accessToken?: string | null; signal?: AbortSignal } = {},
): Promise<TraceListOut> {
  const params = filtersToParams(filters);
  params.set("limit", String(options.limit ?? 50));
  params.set("offset", String(options.offset ?? 0));
  const response = await fetch(`${API_BASE}/api/v1/admin/monitoring/traces?${params}`, {
    headers: authHeaders(options.accessToken),
    signal: options.signal,
  });
  return parseOrThrow(response, "Không thể tải danh sách trace");
}

export async function getTraceDetail(traceId: string, accessToken?: string | null): Promise<TraceDetailOut> {
  const response = await fetch(`${API_BASE}/api/v1/admin/monitoring/traces/${encodeURIComponent(traceId)}`, { headers: authHeaders(accessToken) });
  return parseOrThrow(response, "Không thể tải chi tiết trace");
}

export async function getSessionDetail(conversationId: string, accessToken?: string | null): Promise<SessionDetailOut> {
  const response = await fetch(`${API_BASE}/api/v1/admin/monitoring/sessions/${encodeURIComponent(conversationId)}`, { headers: authHeaders(accessToken) });
  return parseOrThrow(response, "Không thể tải chi tiết phiên hội thoại");
}
