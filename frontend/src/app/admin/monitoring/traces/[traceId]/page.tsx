"use client";

// BUILD-36: Trace detail -- drill-down target from every dashboard section,
// from tickets, and from safety events. Durable metrics ALWAYS available;
// raw query/response text only when `content_available` is true (still in
// the 200-entry in-memory buffer) -- never fabricated/reconstructed when
// it is not (see BUILD-36 report's own audit on this architectural limit).

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertCircle, ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { getTraceDetail, type TraceDetailOut } from "@/lib/admin-monitoring";

export default function TraceDetailPage() {
  const params = useParams<{ traceId: string }>();
  const { accessToken } = useAuth();
  const [detail, setDetail] = useState<TraceDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken || !params.traceId) return;
    setLoading(true);
    getTraceDetail(params.traceId, accessToken)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : "Lỗi không xác định"))
      .finally(() => setLoading(false));
  }, [accessToken, params.traceId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Đang tải...
      </div>
    );
  }
  if (error || !detail) {
    return (
      <div className="surface-card flex items-center gap-2 border-destructive/40 p-4 text-sm text-destructive">
        <AlertCircle className="h-4 w-4" /> {error ?? "Không tìm thấy trace"}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Link href="/admin/monitoring/traces">
        <Button variant="ghost" size="sm"><ArrowLeft className="mr-1 h-4 w-4" /> Quay lại Trace Explorer</Button>
      </Link>

      <div className="surface-card grid grid-cols-2 gap-3 p-4 text-sm md:grid-cols-4">
        <Field label="Trace ID" value={detail.trace_id} mono />
        <Field label="Agent Run ID" value={detail.agent_run_id} mono />
        <Field label="Conversation" value={detail.conversation_id} mono link={detail.conversation_id ? `/admin/monitoring/sessions/${detail.conversation_id}` : undefined} />
        <Field label="Execution path" value={detail.execution_path} />
        <Field label="Intent" value={detail.intent} />
        <Field label="Status" value={detail.status} />
        <Field label="Bắt đầu" value={detail.started_at ? new Date(detail.started_at).toLocaleString("vi-VN") : null} />
        <Field label="Duration (ms)" value={detail.duration_ms?.toString() ?? null} />
        <Field label="Model" value={detail.model} />
        <Field label="Model calls" value={String(detail.model_calls)} />
        <Field label="Prompt version" value={detail.prompt_version} />
        <Field label="Retrieval version" value={detail.retrieval_version} />
        <Field label="Error code" value={detail.error_code} />
        <Field label="Timeout" value={detail.timeout ? "true" : "false"} />
      </div>

      <div className="surface-card p-4">
        <p className="mb-2 text-sm font-medium">Token & Cost</p>
        <p className="text-sm">
          input={detail.tokens.input} cached_input={detail.tokens.cached_input} output={detail.tokens.output} total={detail.tokens.total} -- cost:{" "}
          {detail.cost.status === "AVAILABLE" ? `$${detail.cost.total_usd?.toFixed(6)}` : "N/A"}
        </p>
      </div>

      {detail.spans.length > 0 && (
        <div className="surface-card overflow-x-auto p-4">
          <p className="mb-2 text-sm font-medium">Span timeline (BUILD-32, thật)</p>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted-foreground"><th>Bước</th><th>Loại</th><th>Status</th><th>Duration (ms)</th></tr></thead>
            <tbody>
              {detail.spans.map((s, i) => (
                <tr key={i} className="border-t">
                  <td className="py-1">{s.span_name}</td><td>{s.span_type}</td><td>{s.status}</td><td>{s.duration_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail.evaluation && (
        <div className="surface-card p-4">
          <p className="mb-2 text-sm font-medium">Evaluation V2</p>
          <pre className="overflow-x-auto text-xs">{JSON.stringify(detail.evaluation, null, 2)}</pre>
        </div>
      )}

      {detail.judge && (
        <div className="surface-card p-4">
          <p className="mb-2 text-sm font-medium">Judge</p>
          <p className="text-sm">status={detail.judge.judge_status} score={detail.judge.overall_score ?? "N/A"} model={detail.judge.judge_model} rubric={detail.judge.rubric_version}</p>
        </div>
      )}

      {detail.safety && (
        <div className="surface-card border-rose-500/30 p-4">
          <p className="mb-2 text-sm font-medium text-rose-600">Safety / Handoff</p>
          <p className="text-sm">outcome={detail.safety.outcome} reason_code={detail.safety.reason_code} severity={detail.safety.severity} handoff_required={String(detail.safety.handoff_required)} handoff_created={String(detail.safety.handoff_created)}</p>
        </div>
      )}

      {detail.ticket && (
        <div className="surface-card p-4">
          <p className="mb-2 text-sm font-medium">Ticket</p>
          <Link className="text-primary underline" href={`/admin/tickets/${detail.ticket.ticket_id}`}>{detail.ticket.ticket_id}</Link> -- {detail.ticket.status} ({detail.ticket.reason})
        </div>
      )}

      <div className="surface-card p-4">
        <p className="mb-2 text-sm font-medium">Nội dung (chỉ có khi còn trong buffer)</p>
        {!detail.content_available ? (
          <p className="text-sm text-muted-foreground">Nội dung không còn được lưu tạm (đã hết hạn buffer hoặc tiến trình đã restart) -- các metric ở trên vẫn là dữ liệu thật, durable.</p>
        ) : (
          <div className="space-y-2 text-sm">
            <p><span className="text-muted-foreground">Câu hỏi:</span> {detail.query_preview ?? "N/A"}</p>
            <p><span className="text-muted-foreground">Trả lời:</span> {detail.response_preview ?? "N/A"}</p>
            <p><span className="text-muted-foreground">Tool:</span> {detail.tool_names.join(", ") || "N/A"}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, mono, link }: { label: string; value?: string | null; mono?: boolean; link?: string }) {
  const content = value ?? "N/A";
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      {link ? (
        <Link href={link} className={`text-primary underline ${mono ? "font-mono text-xs" : "text-sm"}`}>{content}</Link>
      ) : (
        <p className={mono ? "font-mono text-xs" : "text-sm"}>{content}</p>
      )}
    </div>
  );
}
