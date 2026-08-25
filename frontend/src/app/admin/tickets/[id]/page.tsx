"use client";

// BUILD-29 §5/§6: ticket detail -> exact conversation/message -> exact
// trace. Trace detail is rendered inline here (same sanitized fields
// GET /admin/rag/traces/{trace_id} already exposes -- intent/tools/tool
// results/Safety-Handoff/model/latency/scores/final response, never hidden
// chain-of-thought) rather than only linking out, since the existing Trace
// Explorer (/admin/rag) has no deep-link/URL state for one specific trace
// (its own "Chi tiết" button is a plain browser alert()) -- a link to it is
// still offered below for the admin who wants the full dashboard context.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  ExternalLink,
  Loader2,
  MessageSquareText,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";
import {
  getFeedbackTicket,
  getFeedbackTicketSession,
  updateFeedbackTicket,
  type FeedbackSession,
  type FeedbackTicketDetail,
  type FeedbackTicketPriority,
  type FeedbackTicketStatus,
} from "@/lib/feedback-tickets";

const REASON_LABELS: Record<string, string> = {
  WRONG_ANSWER: "Trả lời sai",
  NOT_UNDERSTOOD: "Không hiểu câu hỏi",
  WRONG_MEDICATION_INFO: "Sai thông tin thuốc/lịch thuốc",
  UNSAFE_OR_INAPPROPRIATE: "Không phù hợp/an toàn",
  TECHNICAL_ERROR: "Phản hồi bị lỗi",
  OTHER: "Khác",
};

const STATUS_OPTIONS: FeedbackTicketStatus[] = [
  "OPEN",
  "INVESTIGATING",
  "FIXED",
  "CLOSED",
  "WONT_FIX",
];
const PRIORITY_OPTIONS: FeedbackTicketPriority[] = ["P0", "P1", "P2", "P3"];

function formatDateTime(isoString: string | null) {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export default function AdminTicketDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { accessToken } = useAuth();
  const ticketId = params.id;

  const [detail, setDetail] = useState<FeedbackTicketDetail | null>(null);
  const [session, setSession] = useState<FeedbackSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [adminNote, setAdminNote] = useState("");

  const load = () => {
    if (!accessToken || !ticketId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      getFeedbackTicket(ticketId, accessToken),
      getFeedbackTicketSession(ticketId, { accessToken }),
    ])
      .then(([ticketDetail, sessionResult]) => {
        setDetail(ticketDetail);
        setAdminNote(ticketDetail.ticket.admin_note ?? "");
        setSession(sessionResult);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Không thể tải chi tiết báo cáo");
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [accessToken, ticketId]);

  const setField = async (patch: {
    status?: FeedbackTicketStatus;
    priority?: FeedbackTicketPriority;
    admin_note?: string;
  }) => {
    if (!detail) return;
    setSaving(true);
    try {
      const updated = await updateFeedbackTicket(detail.ticket.id, patch, accessToken);
      setDetail({ ...detail, ticket: updated });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể cập nhật báo cáo");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        <Loader2 className="mx-auto h-6 w-6 animate-spin" />
        <p className="mt-2 text-sm">Đang tải chi tiết báo cáo...</p>
      </div>
    );
  }

  if (error && !detail) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
        <AlertCircle className="h-4 w-4" /> {error}
      </div>
    );
  }

  if (!detail) return null;
  const { ticket, trace } = detail;

  return (
    <div className="space-y-6">
      <button
        onClick={() => router.push("/admin/tickets")}
        className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Quay lại danh sách báo cáo
      </button>

      {ticket.p0_review_required && ticket.status === "OPEN" && (
        <div className="flex items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/10 p-4">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <p className="text-sm font-semibold text-destructive">
            P0 — cần xem xét ngay (dấu hiệu an toàn/nguy hiểm cấp tính hoặc người dùng tự đánh giá
            không phù hợp).
          </p>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      <div className="surface-card space-y-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {REASON_LABELS[ticket.reason] ?? ticket.reason} · {ticket.chatbot_version}
            </p>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Báo cáo lúc {formatDateTime(ticket.created_at)}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <FieldSelect
              label="Ưu tiên"
              value={ticket.priority}
              options={PRIORITY_OPTIONS}
              disabled={saving}
              onChange={(v) => setField({ priority: v as FeedbackTicketPriority })}
            />
            <FieldSelect
              label="Trạng thái"
              value={ticket.status}
              options={STATUS_OPTIONS}
              disabled={saving}
              onChange={(v) => setField({ status: v as FeedbackTicketStatus })}
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl bg-muted/40 p-4">
            <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
              Câu hỏi của bệnh nhân
            </p>
            <p className="text-sm">{ticket.user_message}</p>
          </div>
          <div className="rounded-xl bg-muted/40 p-4">
            <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
              Câu trả lời bị báo cáo
            </p>
            <p className="text-sm">{ticket.assistant_message}</p>
          </div>
        </div>

        {ticket.user_note && (
          <div className="rounded-xl border border-border p-4">
            <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
              Ghi chú của bệnh nhân
            </p>
            <p className="text-sm">{ticket.user_note}</p>
          </div>
        )}

        <div className="grid gap-x-6 gap-y-1 text-xs text-muted-foreground sm:grid-cols-2">
          <p>
            Hội thoại: <span className="font-mono">{ticket.conversation_id}</span>
          </p>
          <p>
            Agent run: <span className="font-mono">{ticket.agent_run_id}</span>
          </p>
          <p>
            Trace: <span className="font-mono">{ticket.trace_id ?? "không có"}</span>
          </p>
          <p>
            Bệnh nhân: <span className="font-mono">{ticket.patient_id}</span>
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="admin-note">Ghi chú của Admin</Label>
          <Textarea
            id="admin-note"
            rows={3}
            value={adminNote}
            onChange={(e) => setAdminNote(e.target.value)}
          />
          <Button size="sm" disabled={saving} onClick={() => setField({ admin_note: adminNote })}>
            {saving ? "Đang lưu..." : "Lưu ghi chú"}
          </Button>
        </div>
      </div>

      <div className="surface-card space-y-3 p-5">
        <div className="flex items-center justify-between">
          <h3 className="font-bold">Chi tiết trace liên kết</h3>
          <Link
            href="/admin/rag"
            className="flex items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            Mở Trace Explorer <ExternalLink className="h-3 w-3" />
          </Link>
        </div>
        {!trace.found ? (
          <p className="rounded-lg bg-muted/40 p-4 text-sm text-muted-foreground">
            Trace này không còn trong bộ nhớ tạm của hệ thống (giới hạn 200 trace gần nhất, được
            reset sau mỗi lần deploy) — nội dung câu hỏi/câu trả lời bên trên vẫn là dữ liệu chính
            xác bệnh nhân đã báo cáo.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <InfoRow label="Intent" value={trace.intent ?? "—"} />
            <InfoRow label="Model" value={trace.model ?? "—"} />
            <InfoRow
              label="Độ trễ"
              value={trace.latency_ms != null ? `${trace.latency_ms} ms` : "—"}
            />
            <InfoRow label="Trạng thái trace" value={trace.status ?? "—"} />
            <InfoRow
              label="Công cụ đã gọi"
              value={trace.tools.length ? trace.tools.join(", ") : "không có"}
            />
            <InfoRow
              label="Safety/Handoff"
              value={`${trace.safety_outcome ?? "không có đánh giá"}${trace.handoff_created ? " · đã chuyển bác sĩ" : ""}`}
            />
            {Object.keys(trace.scores).length > 0 && (
              <InfoRow
                label="Scores"
                value={Object.entries(trace.scores)
                  .map(([k, v]) => `${k}=${v}`)
                  .join(", ")}
              />
            )}
            <div className="sm:col-span-2">
              <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                Phản hồi cuối cùng (trace)
              </p>
              <p className="rounded-lg bg-muted/40 p-3 text-sm">{trace.final_response ?? "—"}</p>
            </div>
            {trace.tool_results.length > 0 && (
              <div className="sm:col-span-2">
                <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                  Kết quả công cụ (đã lọc dữ liệu nhạy cảm)
                </p>
                <pre className="max-h-64 overflow-auto rounded-lg bg-muted/40 p-3 text-xs">
                  {JSON.stringify(trace.tool_results, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      {/* BUILD-36: the backend already computed this Judge result (BUILD-33's
          judge_result_out, wired into the route since then) -- this page
          simply never rendered it. Same for Evaluation V2/Safety, both
          genuinely new here (BUILD-36's own audit found neither was ever
          surfaced to ticket detail at all). */}
      {detail.judge && (
        <div className="surface-card space-y-3 p-5">
          <h3 className="font-bold">Kết quả Judge (BUILD-33)</h3>
          <p className="text-xs text-muted-foreground">
            Tín hiệu chất lượng phụ dựa trên LLM. Không phải xác nhận y khoa tuyệt đối.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <InfoRow label="Trạng thái" value={detail.judge.judge_status} />
            <InfoRow label="Model" value={`${detail.judge.judge_provider}:${detail.judge.judge_model}`} />
            <InfoRow label="Rubric" value={`${detail.judge.rubric_name} (${detail.judge.rubric_version})`} />
            <InfoRow label="Điểm tổng" value={detail.judge.overall_score != null ? detail.judge.overall_score.toFixed(2) : "N/A"} />
            {Object.keys(detail.judge.dimension_scores).length > 0 && (
              <div className="sm:col-span-2">
                <p className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Điểm theo tiêu chí</p>
                <p className="text-sm">{Object.entries(detail.judge.dimension_scores).map(([k, v]) => `${k}=${v}`).join(", ")}</p>
              </div>
            )}
            {detail.judge.flags.length > 0 && <InfoRow label="Flags" value={detail.judge.flags.join(", ")} />}
            {detail.judge.failure_reason && <InfoRow label="Lý do lỗi" value={detail.judge.failure_reason} />}
          </div>
        </div>
      )}

      {detail.evaluation && (
        <div className="surface-card space-y-3 p-5">
          <h3 className="font-bold">Evaluation V2 (BUILD-31/32)</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <InfoRow label="Execution path" value={detail.evaluation.execution_path ?? "N/A"} />
            <InfoRow label="Evaluation version" value={detail.evaluation.evaluation_version} />
          </div>
          <pre className="max-h-48 overflow-auto rounded-lg bg-muted/40 p-3 text-xs">{JSON.stringify(detail.evaluation.metrics, null, 2)}</pre>
        </div>
      )}

      {detail.safety && (
        <div className="surface-card space-y-3 border-rose-500/30 p-5">
          <h3 className="font-bold text-rose-600">Safety / Handoff (BUILD-34)</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <InfoRow label="Outcome" value={detail.safety.outcome} />
            <InfoRow label="Reason code" value={detail.safety.reason_code} />
            <InfoRow label="Mức độ" value={detail.safety.severity} />
            <InfoRow label="Handoff required" value={detail.safety.handoff_required ? "có" : "không"} />
            <InfoRow label="Handoff created" value={detail.safety.handoff_created ? "có" : "không"} />
            <InfoRow label="Trạng thái handoff (live)" value={detail.safety.handoff_status_live ?? "N/A"} />
            {detail.safety.assigned_doctor_id && <InfoRow label="Bác sĩ phụ trách" value={detail.safety.assigned_doctor_id} />}
          </div>
        </div>
      )}

      <div className="surface-card space-y-3 p-5">
        <div className="flex items-center gap-2">
          <MessageSquareText className="h-4 w-4 text-muted-foreground" />
          <h3 className="font-bold">Các lượt hội thoại xung quanh (cùng conversation_id)</h3>
        </div>
        {!session || session.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Không còn lượt nào của hội thoại này trong bộ nhớ tạm (cùng giới hạn 200
            trace/reset-sau-deploy nêu trên).
          </p>
        ) : (
          <div className="divide-y divide-border">
            {session.items.map((item) => (
              <div
                key={item.trace_id}
                className={`flex flex-wrap items-start gap-3 py-3 ${item.is_reported_turn ? "rounded-lg bg-warning/10 px-3" : ""}`}
              >
                <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">
                  {formatDateTime(item.timestamp)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{item.query_preview}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {item.final_answer_preview}
                  </p>
                </div>
                {item.is_reported_turn && (
                  <span className="shrink-0 rounded-md bg-warning/25 px-2 py-1 text-xs font-bold text-warning-foreground">
                    Lượt bị báo cáo
                  </span>
                )}
                <span className="shrink-0 font-mono text-xs text-primary">{item.trace_id}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase text-muted-foreground">{label}</p>
      <p className="text-sm">{value}</p>
    </div>
  );
}

function FieldSelect<T extends string>({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: T;
  options: T[];
  disabled?: boolean;
  onChange: (value: T) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
      {label}
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as T)}
        className="h-9 rounded-lg border border-input bg-card px-2 text-sm font-semibold text-foreground outline-none disabled:opacity-60"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  );
}
