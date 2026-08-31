"use client";

import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  CircleUserRound,
  Clock3,
  FileImage,
  HelpCircle,
  ImageIcon,
  LoaderCircle,
  MessageCircleQuestion,
  Send,
  Stethoscope,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth";
import {
  activateDoctorReview,
  cancelDoctorReview,
  claimDoctorReview,
  getDoctorReviewDetail,
  getDoctorReviewImageAttachment,
  resolveDoctorReview,
  sendDoctorReviewMessage,
  type DoctorReviewDetail,
  type DoctorReviewMessage,
} from "@/lib/doctor-reviews";

const TYPE_META: Record<string, { label: string; icon: typeof AlertTriangle; tone: string }> = {
  SAFETY: {
    label: "Cần ưu tiên an toàn",
    icon: AlertTriangle,
    tone: "bg-destructive/10 text-destructive",
  },
  USER_REQUEST: {
    label: "Bệnh nhân yêu cầu",
    icon: MessageCircleQuestion,
    tone: "bg-primary/10 text-primary",
  },
  UNCERTAINTY: {
    label: "Chatbot chưa thể trả lời",
    icon: HelpCircle,
    tone: "bg-warning/20 text-warning-foreground",
  },
};

const STATUS_META: Record<string, { label: string; tone: string }> = {
  PENDING: { label: "Chờ bác sĩ nhận", tone: "bg-muted text-muted-foreground" },
  ASSIGNED: { label: "Đã nhận, chưa bắt đầu", tone: "bg-secondary text-secondary-foreground" },
  ACTIVE: { label: "Đang trao đổi", tone: "bg-success/15 text-success" },
  RESOLVED: { label: "Đã xử lý xong", tone: "bg-success/15 text-success" },
  ANSWERED: { label: "Đã trả lời", tone: "bg-success/15 text-success" },
  CANCELLED: { label: "Đã huỷ", tone: "bg-muted text-muted-foreground" },
};

const SENDER_META: Record<string, { label: string; tone: string }> = {
  PATIENT: { label: "Bệnh nhân", tone: "bg-muted text-foreground" },
  DOCTOR: { label: "Bạn", tone: "bg-primary text-primary-foreground" },
  SYSTEM: { label: "Hệ thống", tone: "bg-secondary text-secondary-foreground" },
};

function formatDateTime(value: string | null): string {
  if (!value) return "Chưa có";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Không rõ thời gian" : date.toLocaleString("vi-VN");
}

function DetailSkeleton() {
  return (
    <div className="space-y-5" aria-label="Đang tải cuộc trao đổi">
      <Skeleton className="h-8 w-44" />
      <div className="surface-card space-y-4 p-5">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-full max-w-2xl" />
      </div>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="surface-card space-y-3 p-5">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-20 w-2/3" />
          <Skeleton className="ml-auto h-16 w-1/2" />
        </div>
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}

function ReviewImageAttachment({
  handoffId,
  attachmentId,
  accessToken,
}: {
  handoffId: string;
  attachmentId: string;
  accessToken?: string | null;
}) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;

    void getDoctorReviewImageAttachment(handoffId, attachmentId, accessToken)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (active) setImageUrl(objectUrl);
        else URL.revokeObjectURL(objectUrl);
      })
      .catch(() => {
        if (active) setError("Không thể tải ảnh riêng tư này.");
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [accessToken, attachmentId, handoffId]);

  if (error) {
    return <p className="mt-2 text-xs text-destructive">{error}</p>;
  }

  if (!imageUrl) {
    return (
      <div className="mt-2 inline-flex items-center gap-2 rounded-md bg-background/70 px-2 py-1.5 text-xs text-muted-foreground">
        <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> Đang tải ảnh riêng tư...
      </div>
    );
  }

  return (
    <a href={imageUrl} target="_blank" rel="noreferrer" className="mt-2 block">
      <img
        src={imageUrl}
        alt="Ảnh bệnh nhân gửi trong cuộc trao đổi"
        className="max-h-72 rounded-lg border border-border object-contain"
      />
      <span className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-primary">
        <FileImage className="h-3.5 w-3.5" /> Mở ảnh kích thước đầy đủ
      </span>
    </a>
  );
}

function ReviewMessageBubble({
  handoffId,
  message,
  accessToken,
}: {
  handoffId: string;
  message: DoctorReviewMessage;
  accessToken?: string | null;
}) {
  const meta = SENDER_META[message.senderRole] ?? {
    label: message.senderRole,
    tone: "bg-muted text-foreground",
  };
  const isDoctor = message.senderRole === "DOCTOR";
  const isSystem = message.senderRole === "SYSTEM";

  if (isSystem) {
    return (
      <div className="flex justify-center py-1">
        <p className="max-w-xl rounded-full bg-muted px-3 py-1.5 text-center text-xs text-muted-foreground">
          {message.content}
        </p>
      </div>
    );
  }

  return (
    <div className={`flex ${isDoctor ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-sm shadow-sm sm:max-w-[78%] ${meta.tone}`}
      >
        <p
          className={`text-[11px] font-bold ${
            isDoctor ? "text-primary-foreground/80" : "text-muted-foreground"
          }`}
        >
          {meta.label} · {formatDateTime(message.createdAt)}
        </p>
        <p className="mt-1 whitespace-pre-wrap leading-6">{message.content}</p>
        {message.imageAttachmentId && (
          <ReviewImageAttachment
            handoffId={handoffId}
            attachmentId={message.imageAttachmentId}
            accessToken={accessToken}
          />
        )}
      </div>
    </div>
  );
}

export default function DoctorReviewDetailPage() {
  const params = useParams<{ id: string }>();
  const handoffId = params.id;
  const router = useRouter();
  const { accessToken, user } = useAuth();
  const [detail, setDetail] = useState<DoctorReviewDetail | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [busyAction, setBusyAction] = useState<
    "claim" | "activate" | "resolve" | "cancel" | "send" | null
  >(null);
  const [draft, setDraft] = useState("");
  const [hasUnreadMessages, setHasUnreadMessages] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const refreshInFlightRef = useRef(false);
  const keepPinnedToBottomRef = useRef(true);
  const priorMessageCountRef = useRef(0);

  const load = useCallback(
    async (silent = false) => {
      if (refreshInFlightRef.current) return;
      refreshInFlightRef.current = true;
      if (silent) setRefreshing(true);
      else {
        setInitialLoading(true);
        setError(null);
      }

      try {
        const next = await getDoctorReviewDetail(handoffId, accessToken);
        setDetail(next);
        setSyncError(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Không tải được yêu cầu.";
        if (silent) setSyncError(message);
        else setError(message);
      } finally {
        refreshInFlightRef.current = false;
        setInitialLoading(false);
        setRefreshing(false);
      }
    },
    [accessToken, handoffId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // Không set initialLoading trong polling: composer, focus và nội dung soạn
  // phải giữ nguyên khi có lượt làm mới nền mỗi 5 giây.
  useEffect(() => {
    if (detail?.status !== "ACTIVE") return;
    const interval = window.setInterval(() => void load(true), 5_000);
    return () => window.clearInterval(interval);
  }, [detail?.status, load]);

  const scrollToLatest = useCallback(() => {
    const thread = threadRef.current;
    if (!thread) return;
    thread.scrollTo({ top: thread.scrollHeight, behavior: "smooth" });
    keepPinnedToBottomRef.current = true;
    setHasUnreadMessages(false);
  }, []);

  useEffect(() => {
    const count = detail?.messages.length ?? 0;
    if (count === priorMessageCountRef.current) return;
    const firstLoad = priorMessageCountRef.current === 0;
    priorMessageCountRef.current = count;

    if (firstLoad || keepPinnedToBottomRef.current) {
      requestAnimationFrame(scrollToLatest);
    } else {
      setHasUnreadMessages(true);
    }
  }, [detail?.messages.length, scrollToLatest]);

  const isMine = user?.doctor_id != null && detail?.assignedDoctorId === user.doctor_id;
  const type = detail
    ? (TYPE_META[detail.handoffType] ?? TYPE_META.UNCERTAINTY)
    : TYPE_META.UNCERTAINTY;
  const status = detail
    ? (STATUS_META[detail.status] ?? {
        label: detail.status,
        tone: "bg-muted text-muted-foreground",
      })
    : null;
  const TypeIcon = type.icon;

  async function runAction(
    action: "claim" | "activate" | "resolve" | "cancel",
    request: () => Promise<DoctorReviewDetail>,
    successMessage: string,
  ) {
    setBusyAction(action);
    try {
      const next = await request();
      setDetail(next);
      toast.success(successMessage);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Thao tác thất bại");
      void load(true);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleSend() {
    const content = draft.trim();
    if (!content) return;
    setBusyAction("send");
    try {
      const next = await sendDoctorReviewMessage(handoffId, content, accessToken);
      setDetail(next);
      setDraft("");
      requestAnimationFrame(scrollToLatest);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gửi tin nhắn thất bại");
    } finally {
      setBusyAction(null);
    }
  }

  function handleThreadScroll() {
    const thread = threadRef.current;
    if (!thread) return;
    const distanceToBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight;
    keepPinnedToBottomRef.current = distanceToBottom < 72;
    if (keepPinnedToBottomRef.current) setHasUnreadMessages(false);
  }

  if (initialLoading) return <DetailSkeleton />;

  if (error || !detail || !status) {
    return (
      <div className="space-y-3">
        <Button variant="ghost" size="sm" onClick={() => router.push("/doctor/reviews")}>
          <ArrowLeft className="h-4 w-4" /> Quay lại hàng đợi
        </Button>
        <div
          className="surface-card flex flex-wrap items-center justify-between gap-3 border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
          role="alert"
        >
          <span>{error ?? "Không tìm thấy yêu cầu."}</span>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            Thử lại
          </Button>
        </div>
      </div>
    );
  }

  const assignedToAnother = detail.assignedDoctorId != null && !isMine;
  const isBusy = busyAction !== null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" size="sm" onClick={() => router.push("/doctor/reviews")}>
          <ArrowLeft className="h-4 w-4" /> Hàng đợi tư vấn
        </Button>
        <div className="flex items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
          {refreshing && <LoaderCircle className="h-3.5 w-3.5 animate-spin" />}
          {refreshing ? "Đang đồng bộ" : "Tự cập nhật"}
        </div>
      </div>

      {syncError && (
        <div
          className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning-foreground"
          role="status"
        >
          Không thể cập nhật tin nhắn mới: {syncError}
        </div>
      )}

      <section className="surface-card overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border p-5">
          <div className="flex min-w-0 items-start gap-3">
            <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${type.tone}`}>
              <TypeIcon className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="truncate text-xl font-bold">{detail.patientName}</h1>
                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${type.tone}`}>
                  {type.label}
                </span>
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${status.tone}`}>
                  {status.label}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">Mã bệnh nhân: {detail.patientId}</p>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            {detail.status === "PENDING" && (
              <Button
                disabled={isBusy}
                onClick={() =>
                  void runAction(
                    "claim",
                    () => claimDoctorReview(handoffId, accessToken),
                    "Đã nhận yêu cầu. Hãy bắt đầu trao đổi khi bạn sẵn sàng.",
                  )
                }
              >
                {busyAction === "claim" ? "Đang nhận..." : "Nhận yêu cầu"}
              </Button>
            )}
            {(detail.status === "PENDING" ||
              (isMine && ["ASSIGNED", "ACTIVE"].includes(detail.status))) && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" disabled={isBusy}>
                    <XCircle className="h-4 w-4" /> Huỷ ca
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Huỷ ca của {detail.patientName}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      {detail.status === "ACTIVE"
                        ? "Trao đổi sẽ kết thúc và chatbot sẽ tiếp tục hỗ trợ ở lượt sau."
                        : "Yêu cầu sẽ không còn trong hàng đợi."}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Quay lại</AlertDialogCancel>
                    <AlertDialogAction
                      disabled={isBusy}
                      onClick={() =>
                        void runAction(
                          "cancel",
                          () => cancelDoctorReview(handoffId, accessToken),
                          "Đã huỷ ca.",
                        )
                      }
                    >
                      Xác nhận huỷ
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
            {detail.status === "ASSIGNED" && isMine && (
              <Button
                disabled={isBusy}
                onClick={() =>
                  void runAction(
                    "activate",
                    () => activateDoctorReview(handoffId, accessToken),
                    "Đã bắt đầu trao đổi với bệnh nhân.",
                  )
                }
              >
                <Stethoscope className="h-4 w-4" />
                {busyAction === "activate" ? "Đang bắt đầu..." : "Bắt đầu trao đổi"}
              </Button>
            )}
            {detail.status === "ACTIVE" && isMine && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" disabled={isBusy}>
                    <CheckCircle2 className="h-4 w-4" /> Kết thúc trao đổi
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Kết thúc trao đổi với {detail.patientName}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Bạn sẽ không thể gửi thêm tin nhắn trong ca này. Ở lượt nhắn tiếp theo,
                      chatbot sẽ tiếp tục hỗ trợ bệnh nhân theo luồng thông thường.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Quay lại trao đổi</AlertDialogCancel>
                    <AlertDialogAction
                      disabled={isBusy}
                      onClick={() =>
                        void runAction(
                          "resolve",
                          () => resolveDoctorReview(handoffId, accessToken),
                          "Đã kết thúc trao đổi. Chatbot sẽ tiếp tục hỗ trợ ở lượt sau.",
                        )
                      }
                    >
                      Xác nhận kết thúc
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>
        </div>

        <div className="grid gap-3 bg-muted/35 p-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <p>
            <span className="block text-xs text-muted-foreground">Trạng thái phụ trách</span>
            <span className="mt-1 inline-flex items-center gap-1.5 font-semibold">
              <CircleUserRound className="h-4 w-4 text-primary" />
              {isMine
                ? "Bạn đang phụ trách ca này"
                : assignedToAnother
                  ? "Bác sĩ khác đang phụ trách"
                  : "Chưa có bác sĩ nhận ca"}
            </span>
          </p>
          <p>
            <span className="block text-xs text-muted-foreground">Chuyển tới lúc</span>
            <span className="mt-1 inline-flex items-center gap-1.5 font-semibold">
              <Clock3 className="h-4 w-4 text-primary" /> {formatDateTime(detail.createdAt)}
            </span>
          </p>
          <Link
            href={`/doctor/patients?q=${encodeURIComponent(detail.patientId)}`}
            className="inline-flex items-center gap-1.5 self-end font-semibold text-primary hover:underline"
          >
            <CircleUserRound className="h-4 w-4" /> Mở hồ sơ bệnh nhân
          </Link>
        </div>
      </section>

      <section className="surface-card p-5">
        <h2 className="mb-3 font-bold">Lịch sử chat với Capy</h2>
        <div className="max-h-64 space-y-2 overflow-y-auto rounded-lg bg-muted/50 p-3">
          {detail.chatHistory.length === 0 ? (
            <p className="text-sm text-muted-foreground">Chưa có lịch sử chatbot được lưu.</p>
          ) : (
            detail.chatHistory.map((message) => (
              <div
                key={message.id}
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  message.role === "patient"
                    ? "ml-auto bg-primary text-primary-foreground"
                    : "bg-background text-foreground"
                }`}
              >
                <p className="m-0 whitespace-pre-wrap">{message.content}</p>
                <p className="mt-1 text-[10px] opacity-70">{formatDateTime(message.createdAt)}</p>
              </div>
            ))
          )}
        </div>
      </section>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <section className="surface-card relative overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
            <h2 className="font-bold">Cuộc trao đổi</h2>
            {detail.status === "ACTIVE" && isMine && (
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-success">
                <span className="h-2 w-2 rounded-full bg-success" /> Đang nhận tin nhắn mới
              </span>
            )}
          </div>

          <div
            ref={threadRef}
            onScroll={handleThreadScroll}
            className="max-h-[min(52vh,36rem)] space-y-3 overflow-y-auto px-5 py-5"
            aria-live="polite"
            aria-label="Luồng tin nhắn trao đổi với bệnh nhân"
          >
            {detail.messages.length === 0 && (
              <div className="py-10 text-center">
                <MessageCircleQuestion className="mx-auto h-9 w-9 text-muted-foreground/40" />
                <p className="mt-2 text-sm font-semibold">Chưa có tin nhắn trong ca này</p>
              </div>
            )}
            {detail.messages.map((message) => (
              <ReviewMessageBubble
                key={message.id}
                handoffId={handoffId}
                message={message}
                accessToken={accessToken}
              />
            ))}
          </div>

          {hasUnreadMessages && (
            <div className="absolute bottom-24 left-1/2 -translate-x-1/2">
              <Button size="sm" className="rounded-full shadow-lg" onClick={scrollToLatest}>
                Tin nhắn mới <ChevronDown className="h-4 w-4" />
              </Button>
            </div>
          )}

          {detail.status === "ACTIVE" && isMine ? (
            <div className="border-t border-border bg-background p-4 sm:p-5">
              <label className="block">
                <span className="mb-2 block text-sm font-semibold">Phản hồi cho bệnh nhân</span>
                <div className="flex items-end gap-2">
                  <Textarea
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="Nhập phản hồi cho bệnh nhân…"
                    className="min-h-[84px] flex-1 resize-y"
                    disabled={isBusy}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing
                      ) {
                        event.preventDefault();
                        void handleSend();
                      }
                    }}
                  />
                  <Button
                    className="mb-0.5 shrink-0"
                    onClick={() => void handleSend()}
                    disabled={isBusy || !draft.trim()}
                    aria-label="Gửi phản hồi cho bệnh nhân"
                  >
                    {busyAction === "send" ? <LoaderCircle className="animate-spin" /> : <Send />}
                    <span className="hidden sm:inline">Gửi</span>
                  </Button>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  Enter để gửi · Shift + Enter để xuống dòng
                </p>
              </label>
            </div>
          ) : (
            <div className="border-t border-border bg-muted/30 px-5 py-4 text-sm text-muted-foreground">
              {["RESOLVED", "CANCELLED"].includes(detail.status)
                ? "Ca đã kết thúc. Chatbot sẽ tiếp tục hỗ trợ ở lượt nhắn tiếp theo."
                : assignedToAnother
                  ? "Bác sĩ khác đang phụ trách ca này nên bạn chỉ có thể xem nội dung trao đổi."
                  : detail.status === "ANSWERED"
                    ? "Ca đã được trả lời."
                    : "Nhận và bắt đầu trao đổi để gửi phản hồi."}
            </div>
          )}
        </section>

        <aside className="space-y-4 xl:sticky xl:top-[86px]">
          <section className="surface-card p-5">
            <div className="flex items-center gap-2">
              <ImageIcon className="h-4 w-4 text-primary" />
              <h2 className="font-bold">Tình huống ban đầu</h2>
            </div>
            <blockquote className="mt-3 border-l-2 border-primary/40 pl-3 text-sm leading-6 text-foreground">
              “{detail.patientQuestion}”
            </blockquote>
          </section>

          <section className="surface-card p-5">
            <h2 className="font-bold">Mốc xử lý</h2>
            <ol className="mt-4 space-y-4 border-l border-border pl-4 text-sm">
              <li className="relative">
                <span className="absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full bg-primary" />
                <p className="font-semibold">Yêu cầu được chuyển</p>
                <p className="text-xs text-muted-foreground">{formatDateTime(detail.createdAt)}</p>
              </li>
              {detail.assignedAt && (
                <li className="relative">
                  <span className="absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full bg-primary" />
                  <p className="font-semibold">Bác sĩ đã nhận</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(detail.assignedAt)}
                  </p>
                </li>
              )}
              {detail.activatedAt && (
                <li className="relative">
                  <span className="absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full bg-success" />
                  <p className="font-semibold">Bắt đầu trao đổi</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(detail.activatedAt)}
                  </p>
                </li>
              )}
              {detail.resolvedAt && (
                <li className="relative">
                  <span className="absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full bg-success" />
                  <p className="font-semibold">Đã kết thúc</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(detail.resolvedAt)}
                  </p>
                </li>
              )}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  );
}
