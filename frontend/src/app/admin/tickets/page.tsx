"use client";

// BUILD-29 §5: "Chatbot Issues / User Reports" - danh sach ticket bao cao
// tu benh nhan, filter theo status/priority/reason/chatbot_version/ngay.
// Click 1 ticket mo trang chi tiet (/admin/tickets/[id]) - noi that su noi
// ticket -> conversation -> trace, khong lam lai o day.

import Link from "next/link";
import { AlertCircle, AlertTriangle, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { listFeedbackTickets, type FeedbackTicket } from "@/lib/feedback-tickets";

const REASON_LABELS: Record<string, string> = {
  WRONG_ANSWER: "Trả lời sai",
  NOT_UNDERSTOOD: "Không hiểu câu hỏi",
  WRONG_MEDICATION_INFO: "Sai thông tin thuốc/lịch thuốc",
  UNSAFE_OR_INAPPROPRIATE: "Không phù hợp/an toàn",
  TECHNICAL_ERROR: "Phản hồi bị lỗi",
  OTHER: "Khác",
};

const STATUS_LABELS: Record<string, string> = {
  OPEN: "Mới",
  INVESTIGATING: "Đang xử lý",
  FIXED: "Đã sửa",
  CLOSED: "Đã đóng",
  WONT_FIX: "Không sửa",
};

const STATUS_TONE: Record<string, string> = {
  OPEN: "bg-warning/20 text-warning-foreground",
  INVESTIGATING: "bg-primary/10 text-primary",
  FIXED: "bg-success/15 text-success",
  CLOSED: "bg-muted text-muted-foreground",
  WONT_FIX: "bg-muted text-muted-foreground",
};

const PRIORITY_TONE: Record<string, string> = {
  P0: "bg-destructive/15 text-destructive",
  P1: "bg-warning/25 text-warning-foreground",
  P2: "bg-primary/10 text-primary",
  P3: "bg-muted text-muted-foreground",
};

function formatDateTime(isoString: string) {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export default function AdminTicketsPage() {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState("all");
  const [priority, setPriority] = useState("all");
  const [reason, setReason] = useState("all");
  const [page, setPage] = useState(0);
  const pageSize = 20;
  const [items, setItems] = useState<FeedbackTicket[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    listFeedbackTickets({
      status,
      priority,
      reason,
      limit: pageSize,
      offset: page * pageSize,
      accessToken,
      signal: controller.signal,
    })
      .then((result) => {
        setItems(result.items);
        setTotal(result.total);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Không thể tải danh sách báo cáo");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [accessToken, status, priority, reason, page]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const changeFilter = (setter: (v: string) => void) => (v: string) => {
    setter(v);
    setPage(0);
  };

  const p0Count = items.filter((t) => t.p0_review_required && t.status === "OPEN").length;

  return (
    <div className="space-y-6">
      {p0Count > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-destructive/40 bg-destructive/10 p-4">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <p className="text-sm text-destructive">
            Có {p0Count} báo cáo P0 cần xem xét ngay trên trang này (dấu hiệu an toàn/nguy hiểm cấp
            tính).
          </p>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <select
          value={status}
          onChange={(e) => changeFilter(setStatus)(e.target.value)}
          aria-label="Lọc theo trạng thái"
          className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
        >
          <option value="all">Trạng thái: Tất cả</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          value={priority}
          onChange={(e) => changeFilter(setPriority)(e.target.value)}
          aria-label="Lọc theo mức ưu tiên"
          className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
        >
          <option value="all">Ưu tiên: Tất cả</option>
          <option value="P0">P0</option>
          <option value="P1">P1</option>
          <option value="P2">P2</option>
          <option value="P3">P3</option>
        </select>
        <select
          value={reason}
          onChange={(e) => changeFilter(setReason)(e.target.value)}
          aria-label="Lọc theo lý do"
          className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
        >
          <option value="all">Lý do: Tất cả</option>
          {Object.entries(REASON_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      <div className="surface-card divide-y divide-border">
        {loading ? (
          <div className="p-8 text-center text-muted-foreground">
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
            <p className="mt-2 text-sm">Đang tải danh sách báo cáo...</p>
          </div>
        ) : items.length === 0 ? (
          <p className="p-8 text-center text-muted-foreground">
            Không có báo cáo nào phù hợp bộ lọc.
          </p>
        ) : (
          items.map((t) => (
            <Link
              key={t.id}
              href={`/admin/tickets/${t.id}`}
              className="flex flex-wrap items-start gap-4 p-4 transition-colors hover:bg-muted/40"
            >
              <div className="w-32 shrink-0">
                <p className="text-sm font-semibold">{formatDateTime(t.created_at)}</p>
                <p className="font-mono text-xs text-muted-foreground">{t.chatbot_version}</p>
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{t.assistant_message}</p>
                <p className="mt-0.5 truncate text-sm text-muted-foreground">
                  Câu hỏi: {t.user_message}
                </p>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  Hội thoại {t.conversation_id}
                  {t.trace_id ? ` · trace ${t.trace_id}` : " · trace không còn trong bộ nhớ"}
                </p>
              </div>
              <span className="shrink-0 rounded-md bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground">
                {REASON_LABELS[t.reason] ?? t.reason}
              </span>
              <span
                className={`shrink-0 rounded-md px-2 py-1 text-xs font-bold ${PRIORITY_TONE[t.priority] ?? "bg-muted text-muted-foreground"}`}
              >
                {t.priority}
              </span>
              <span
                className={`shrink-0 rounded-md px-2 py-1 text-xs font-semibold ${STATUS_TONE[t.status] ?? "bg-muted text-muted-foreground"}`}
              >
                {STATUS_LABELS[t.status] ?? t.status}
              </span>
            </Link>
          ))
        )}
      </div>

      {totalPages > 1 && (
        <nav aria-label="Phân trang" className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">Tổng cộng {total} báo cáo</p>
          <div className="flex items-center gap-2">
            <button
              aria-label="Trang trước"
              disabled={page <= 0 || loading}
              onClick={() => setPage((p) => p - 1)}
              className="grid h-9 w-9 place-items-center rounded-lg border border-input text-muted-foreground disabled:opacity-40"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm text-muted-foreground">
              Trang {page + 1}/{totalPages}
            </span>
            <button
              aria-label="Trang sau"
              disabled={page + 1 >= totalPages || loading}
              onClick={() => setPage((p) => p + 1)}
              className="grid h-9 w-9 place-items-center rounded-lg border border-input text-muted-foreground disabled:opacity-40"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </nav>
      )}
    </div>
  );
}
