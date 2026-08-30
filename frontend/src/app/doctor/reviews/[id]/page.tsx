"use client";

import { ArrowLeft, Send } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";
import {
  activateDoctorReview,
  claimDoctorReview,
  getDoctorReviewDetail,
  resolveDoctorReview,
  sendDoctorReviewMessage,
  type DoctorReviewDetail,
} from "@/lib/doctor-reviews";

// BUILD-44: khong gian lam viec cua 1 handoff - nhan -> bat dau -> tro
// chuyen -> ket thuc. Tin nhan bac si go o day duoc luu NGUYEN VAN, khong
// qua Main Model (xem backend/api/doctor_review_routes.py::send_doctor_message).

const TYPE_LABEL: Record<string, string> = {
  SAFETY: "An toàn",
  USER_REQUEST: "Yêu cầu trực tiếp",
  UNCERTAINTY: "Chưa rõ ràng",
};

const STATUS_LABEL: Record<string, string> = {
  PENDING: "Chờ nhận",
  ASSIGNED: "Đã nhận, chưa bắt đầu",
  ACTIVE: "Đang trao đổi",
  RESOLVED: "Đã xử lý xong",
  ANSWERED: "Đã trả lời",
  CANCELLED: "Đã huỷ",
};

const SENDER_LABEL: Record<string, string> = {
  PATIENT: "Bệnh nhân",
  DOCTOR: "Bác sĩ",
  SYSTEM: "Hệ thống",
};

export default function DoctorReviewDetailPage() {
  const params = useParams<{ id: string }>();
  const handoffId = params.id;
  const router = useRouter();
  const { accessToken, user } = useAuth();

  const [detail, setDetail] = useState<DoctorReviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getDoctorReviewDetail(handoffId, accessToken)
      .then(setDetail)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [handoffId, accessToken]);

  useEffect(() => {
    load();
  }, [load]);

  // Trong luc ACTIVE, poll nhe de thay tin nhan/trang thai moi cua benh
  // nhan - khong co WebSocket rieng cho luong nay (thanh that ghi trong
  // report BUILD-44 SS18, khong gia vo la real-time).
  useEffect(() => {
    if (detail?.status !== "ACTIVE") return;
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [detail?.status, load]);

  const isMine = user?.doctor_id != null && detail?.assignedDoctorId === user.doctor_id;

  async function run(action: () => Promise<DoctorReviewDetail>, successMessage: string) {
    setBusy(true);
    try {
      const next = await action();
      setDetail(next);
      toast.success(successMessage);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Thao tác thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function handleSend() {
    const content = draft.trim();
    if (!content) return;
    setBusy(true);
    try {
      const next = await sendDoctorReviewMessage(handoffId, content, accessToken);
      setDetail(next);
      setDraft("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gửi tin nhắn thất bại");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Đang tải...</p>;
  }
  if (error || !detail) {
    return (
      <div className="space-y-3">
        <Button variant="ghost" size="sm" onClick={() => router.push("/doctor/reviews")}>
          <ArrowLeft className="h-4 w-4" /> Quay lại hàng đợi
        </Button>
        <div className="surface-card border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error ?? "Không tìm thấy yêu cầu."}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Button variant="ghost" size="sm" onClick={() => router.push("/doctor/reviews")}>
        <ArrowLeft className="h-4 w-4" /> Quay lại hàng đợi
      </Button>

      <div className="surface-card space-y-3 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold">{detail.patientName}</h1>
            <p className="text-xs text-muted-foreground">
              {TYPE_LABEL[detail.handoffType] ?? detail.handoffType} ·{" "}
              {STATUS_LABEL[detail.status] ?? detail.status}
              {detail.assignedDoctorId && !isMine && " · đã được bác sĩ khác nhận"}
            </p>
          </div>
          <div className="flex gap-2">
            {detail.status === "PENDING" && (
              <Button
                size="sm"
                disabled={busy}
                onClick={() =>
                  run(() => claimDoctorReview(handoffId, accessToken), "Đã nhận yêu cầu")
                }
              >
                Nhận yêu cầu
              </Button>
            )}
            {detail.status === "ASSIGNED" && isMine && (
              <Button
                size="sm"
                disabled={busy}
                onClick={() =>
                  run(() => activateDoctorReview(handoffId, accessToken), "Đã bắt đầu trao đổi")
                }
              >
                Bắt đầu trao đổi
              </Button>
            )}
            {detail.status === "ACTIVE" && isMine && (
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  run(() => resolveDoctorReview(handoffId, accessToken), "Đã kết thúc trao đổi")
                }
              >
                Kết thúc trao đổi
              </Button>
            )}
          </div>
        </div>
        <div className="rounded-lg bg-muted p-3 text-sm">
          <p className="font-semibold">Câu hỏi/tình huống ban đầu:</p>
          <p className="mt-1 text-muted-foreground">{detail.patientQuestion}</p>
        </div>
      </div>

      <div className="surface-card p-5">
        <h2 className="mb-3 font-bold">Lịch sử chat với Capy</h2>
        <div className="mb-5 max-h-64 space-y-2 overflow-y-auto rounded-lg bg-muted/50 p-3">
          {detail.chatHistory.length === 0 ? (
            <p className="text-sm text-muted-foreground">Chưa có lịch sử chatbot được lưu.</p>
          ) : (
            detail.chatHistory.map((message) => (
              <div key={message.id} className={`flex ${message.role === "patient" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${message.role === "patient" ? "bg-primary/10" : "bg-background"}`}>
                  <p className="text-[11px] font-semibold text-muted-foreground">
                    {message.role === "patient" ? "Bệnh nhân" : "Capy"} · {new Date(message.createdAt).toLocaleString("vi-VN")}
                  </p>
                  <p className="mt-0.5 whitespace-pre-wrap">{message.content}</p>
                </div>
              </div>
            ))
          )}
        </div>
        <h2 className="mb-3 font-bold">Tin nhắn</h2>
        <div className="max-h-[28rem] space-y-3 overflow-y-auto">
          {detail.messages.length === 0 && (
            <p className="text-sm text-muted-foreground">Chưa có tin nhắn nào.</p>
          )}
          {detail.messages.map((m) => (
            <div
              key={m.id}
              className={`flex ${m.senderRole === "DOCTOR" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  m.senderRole === "DOCTOR" ? "bg-primary/10" : "bg-muted"
                }`}
              >
                <p className="text-[11px] font-semibold text-muted-foreground">
                  {SENDER_LABEL[m.senderRole] ?? m.senderRole} ·{" "}
                  {new Date(m.createdAt).toLocaleString("vi-VN")}
                </p>
                <p className="mt-0.5 whitespace-pre-wrap">{m.content}</p>
              </div>
            </div>
          ))}
        </div>

        {detail.status === "ACTIVE" && isMine ? (
          <div className="mt-4 flex gap-2">
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Nhập phản hồi cho bệnh nhân..."
              className="min-h-[60px]"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
            <Button onClick={handleSend} disabled={busy || !draft.trim()}>
              <Send className="h-4 w-4" /> Gửi
            </Button>
          </div>
        ) : (
          <p className="mt-4 text-xs text-muted-foreground">
            {detail.status === "RESOLVED"
              ? "Yêu cầu đã kết thúc - chatbot đã tiếp tục hỗ trợ bệnh nhân bình thường."
              : "Bắt đầu trao đổi để gửi tin nhắn cho bệnh nhân."}
          </p>
        )}
      </div>

      <p className="text-center text-xs text-muted-foreground">
        <Link href="/doctor/reviews" className="hover:underline">
          Xem toàn bộ hàng đợi
        </Link>
      </p>
    </div>
  );
}
