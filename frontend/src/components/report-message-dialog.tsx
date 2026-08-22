"use client";

// BUILD-29 §2: "Báo cáo câu trả lời" - nut bao cao mot tin nhan assistant cu
// the. Khong bao gio hoi nguoi dung nhap trace/session id thu cong - toan bo
// metadata (conversation_id/trace_id/agent_run_id/userMessage) da duoc luu
// san tren chinh StoredChatMessage nay tu luc nhan phan hoi that (xem
// frontend/src/lib/chat-history.ts va app/patient/assistant/page.tsx).

import { useState } from "react";
import { CheckCircle2, Flag } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { submitFeedbackReport } from "@/lib/api";
import type { StoredChatMessage } from "@/lib/chat-history";
import type { FeedbackReason } from "@/types/chat";

const REASON_OPTIONS: { value: FeedbackReason; label: string }[] = [
  { value: "WRONG_ANSWER", label: "Trả lời sai" },
  { value: "NOT_UNDERSTOOD", label: "Không hiểu câu hỏi" },
  { value: "WRONG_MEDICATION_INFO", label: "Sai thông tin thuốc/lịch thuốc" },
  { value: "UNSAFE_OR_INAPPROPRIATE", label: "Câu trả lời không phù hợp/an toàn" },
  { value: "TECHNICAL_ERROR", label: "Phản hồi bị lỗi" },
  { value: "OTHER", label: "Khác" },
];

export function ReportMessageDialog({
  conversationId,
  message,
  accessToken,
}: {
  conversationId: string;
  message: StoredChatMessage;
  accessToken?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<FeedbackReason>("WRONG_ANSWER");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  const resetState = () => {
    setReason("WRONG_ANSWER");
    setNote("");
    setLoading(false);
    setSuccess(false);
    setError("");
  };

  const submit = async () => {
    setLoading(true);
    setError("");
    try {
      await submitFeedbackReport(
        {
          conversation_id: conversationId,
          trace_id: message.traceId ?? null,
          agent_run_id: message.agentRunId ?? "",
          user_message: message.userMessage ?? "",
          assistant_message: message.content,
          reason,
          user_note: note.trim() || null,
        },
        accessToken,
      );
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể gửi báo cáo. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  };

  // Khong the bao cao mot tin nhan chua co agent_run_id that (vi du tin nhan
  // he thong chen tinh, khong tu mot phan hoi Agent V2 that - xem
  // symptomCheckPending trong assistant/page.tsx) - an nut trong truong hop
  // do thay vi de nguoi dung bam roi that bai kho hieu.
  if (!message.agentRunId) return null;

  return (
    <Dialog
      open={open}
      onOpenChange={(val) => {
        setOpen(val);
        if (!val) resetState();
      }}
    >
      <button
        onClick={() => setOpen(true)}
        className="mt-1 flex items-center gap-1 self-start px-1 text-[10px] font-medium text-[#8A7BC0] transition-colors hover:text-[#4B3E86]"
      >
        <Flag className="h-2.5 w-2.5" /> Báo cáo câu trả lời
      </button>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Flag className="h-5 w-5 text-primary" /> Báo cáo câu trả lời
          </DialogTitle>
          <DialogDescription>
            Cho chúng tôi biết vấn đề với câu trả lời này để đội ngũ hỗ trợ kiểm tra lại.
          </DialogDescription>
        </DialogHeader>

        {!success ? (
          <div className="space-y-4 py-2">
            {error && (
              <div className="rounded-lg bg-destructive/15 p-3 text-sm font-medium text-destructive">
                {error}
              </div>
            )}

            <RadioGroup value={reason} onValueChange={(v) => setReason(v as FeedbackReason)}>
              {REASON_OPTIONS.map((opt) => (
                <div key={opt.value} className="flex items-center space-x-2 py-1">
                  <RadioGroupItem value={opt.value} id={`reason-${opt.value}`} />
                  <Label htmlFor={`reason-${opt.value}`} className="cursor-pointer font-normal">
                    {opt.label}
                  </Label>
                </div>
              ))}
            </RadioGroup>

            <div className="space-y-2">
              <Label htmlFor="report-note">Ghi chú thêm (không bắt buộc)</Label>
              <Textarea
                id="report-note"
                placeholder="Mô tả ngắn gọn vấn đề bạn gặp phải..."
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={1000}
                rows={3}
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                Hủy
              </Button>
              <Button type="button" onClick={submit} disabled={loading}>
                {loading ? "Đang gửi..." : "Gửi báo cáo"}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4 py-6 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-success/15 text-success">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <p className="text-base font-semibold">Đã gửi báo cáo!</p>
            <p className="text-sm text-muted-foreground">
              Cảm ơn bạn đã phản hồi. Đội ngũ hỗ trợ sẽ kiểm tra lại câu trả lời này.
            </p>
            <Button
              className="w-full"
              onClick={() => {
                setOpen(false);
                resetState();
              }}
            >
              Đóng
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
