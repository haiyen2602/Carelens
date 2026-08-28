"use client";

// BUILD-36: Session Explorer -- ordered turn-by-turn view of one
// conversation. Reuses the SAME agent_feedback.session_messages merge
// (ring buffer + durable AgentRun fallback) BUILD-29's own ticket session
// sub-route already uses -- not a second, independent implementation.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertCircle, ArrowLeft, LayoutDashboard, ListFilter, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { getSessionDetail, type SessionDetailOut } from "@/lib/admin-monitoring";

// Matches backend.models.schemas.AgentFeedbackSessionMessageOut exactly.
type SessionMessage = {
  trace_id: string;
  timestamp: string;
  query_preview: string;
  final_answer_preview: string;
  status: string;
  is_reported_turn: boolean;
};

export default function SessionDetailPage() {
  const params = useParams<{ conversationId: string }>();
  const router = useRouter();
  const { accessToken } = useAuth();
  const [data, setData] = useState<SessionDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken || !params.conversationId) return;
    setLoading(true);
    getSessionDetail(params.conversationId, accessToken)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Lỗi không xác định"))
      .finally(() => setLoading(false));
  }, [accessToken, params.conversationId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Đang tải phiên hội thoại...
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Quay lại
          </Button>
        </div>
        <div className="surface-card flex items-center gap-2 border-destructive/40 p-4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> {error ?? "Không tải được phiên hội thoại"}
        </div>
      </div>
    );
  }

  const items = data.items as SessionMessage[];

  return (
    <div className="space-y-4">
      {/* Navigation bar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              if (window.history.length > 1) {
                router.back();
              } else {
                router.push("/admin/monitoring/traces");
              }
            }}
          >
            <ArrowLeft className="mr-1 h-4 w-4" /> Quay lại trang trước
          </Button>
          <Link href="/admin/monitoring/traces">
            <Button variant="ghost" size="sm">
              <ListFilter className="mr-1 h-4 w-4" /> Danh sách Trace
            </Button>
          </Link>
        </div>
        <Link href="/admin/monitoring">
          <Button variant="ghost" size="sm" className="text-muted-foreground">
            <LayoutDashboard className="mr-1 h-4 w-4" /> Bảng điều khiển Giám sát
          </Button>
        </Link>
      </div>

      <div>
        <h1 className="text-xl font-semibold">Phiên hội thoại</h1>
        <p className="font-mono text-xs text-muted-foreground">{params.conversationId}</p>
      </div>
      {!data.available && (
        <div className="surface-card p-4 text-sm text-muted-foreground">Dữ liệu hiện không khả dụng.</div>
      )}
      {data.available && items.length === 0 && (
        <div className="surface-card p-4 text-sm text-muted-foreground">Không có lượt hội thoại nào.</div>
      )}
      <div className="space-y-3">
        {items.map((item, idx) => (
          <div key={item.trace_id ?? idx} className={`surface-card p-4 ${item.is_reported_turn ? "border-amber-500/40" : ""}`}>
            <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>{item.timestamp ? new Date(item.timestamp).toLocaleString("vi-VN") : "N/A"} -- {item.status ?? "N/A"}{item.is_reported_turn ? " -- đã bị báo cáo" : ""}</span>
              {item.trace_id && (
                <Link className="text-primary underline" href={`/admin/monitoring/traces/${item.trace_id}`}>trace →</Link>
              )}
            </div>
            <p className="text-sm"><span className="text-muted-foreground">Người dùng:</span> {item.query_preview ?? "N/A"}</p>
            <p className="text-sm"><span className="text-muted-foreground">Trợ lý:</span> {item.final_answer_preview ?? "N/A"}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
