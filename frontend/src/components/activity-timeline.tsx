"use client";

// BUILD-30 §4: "Xem hoạt động" - collapse mac dinh, fetch tu that trace cua
// DUNG message nay khi nguoi dung bam mo (khong fetch san cho moi tin nhan -
// item 8: "chi can post-response timeline", khong can preload/streaming).
// Loi khi fetch KHONG duoc lam hong chat bubble - chi hien 1 dong loi nho
// ben trong khu vuc activity, phan con lai cua tin nhan van hien thi binh
// thuong (xem cach dung trong chat-message.tsx).

import { useState } from "react";
import { AlertCircle, CheckCircle2, ChevronDown, Loader2, XCircle } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { getTraceActivity } from "@/lib/api";
import type { ActivityItem } from "@/types/chat";

type LoadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "loaded"; activities: ActivityItem[] }
  | { kind: "unavailable" }
  | { kind: "error"; message: string };

// "blocked"/"pending"/"failed" van la trang thai THAT (xem
// backend/services/agent_activity.py) - hien icon khac "completed" thay vi
// gia vo moi buoc deu thanh cong.
function iconFor(status: string) {
  if (status === "completed") return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" />;
  if (status === "failed") return <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />;
  return <AlertCircle className="h-3.5 w-3.5 shrink-0 text-warning-foreground" />;
}

export function ActivityTimeline({
  traceId,
  accessToken,
}: {
  traceId?: string;
  accessToken?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<LoadState>({ kind: "idle" });

  // Tin nhan he thong chen tinh (symptomCheckPending trong assistant/page.tsx)
  // khong co trace_id that - an ca nut nay, giong ReportMessageDialog.
  if (!traceId) return null;

  const load = () => {
    if (state.kind === "loading" || state.kind === "loaded") return;
    setState({ kind: "loading" });
    getTraceActivity(traceId, accessToken)
      .then((res) => {
        setState(
          res.available ? { kind: "loaded", activities: res.activities } : { kind: "unavailable" },
        );
      })
      .catch(() => {
        setState({ kind: "error", message: "Không thể tải hoạt động. Vui lòng thử lại." });
      });
  };

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) load();
      }}
      className="mt-1 self-start"
    >
      <CollapsibleTrigger className="flex items-center gap-1 px-1 text-[10px] font-medium text-[#8A7BC0] transition-colors hover:text-[#4B3E86]">
        Xem hoạt động
        <ChevronDown className={`h-2.5 w-2.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1.5 max-w-[82%] rounded-2xl bg-white/70 px-3 py-2 text-[11px]">
        {state.kind === "loading" && (
          <p className="flex items-center gap-1.5 text-[#8A7BC0]">
            <Loader2 className="h-3 w-3 animate-spin" /> Đang tải hoạt động...
          </p>
        )}
        {state.kind === "unavailable" && (
          <p className="text-[#8A7BC0]">Chi tiết hoạt động hiện không còn khả dụng.</p>
        )}
        {state.kind === "error" && <p className="text-destructive">{state.message}</p>}
        {state.kind === "loaded" && (
          <ul className="space-y-1">
            {state.activities.map((item, idx) => (
              <li key={idx} className="flex items-start gap-1.5 text-[#4B3E86]">
                {iconFor(item.status)}
                <span>
                  {item.label}
                  {typeof item.source_count === "number" &&
                    item.source_count > 0 &&
                    ` (${item.source_count} nguồn)`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
