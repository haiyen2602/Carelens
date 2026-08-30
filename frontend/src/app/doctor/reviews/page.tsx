"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  HelpCircle,
  Inbox,
  MessageCircleQuestion,
  RefreshCw,
  Search,
  UserCheck,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import {
  claimDoctorReview,
  listDoctorReviewQueue,
  type DoctorReviewQueueItem,
} from "@/lib/doctor-reviews";

// BUILD-44 chỉ cung cấp loại handoff đã được quyết định ở backend. Trang này
// sắp xếp và diễn đạt lại cho bác sĩ, tuyệt đối không tự suy ra mức nguy cơ.
const TYPE_META: Record<
  string,
  { label: string; icon: typeof AlertTriangle; tone: string; accent: string }
> = {
  SAFETY: {
    label: "Cần ưu tiên an toàn",
    icon: AlertTriangle,
    tone: "bg-destructive/10 text-destructive",
    accent: "border-l-destructive",
  },
  USER_REQUEST: {
    label: "Bệnh nhân yêu cầu",
    icon: MessageCircleQuestion,
    tone: "bg-primary/10 text-primary",
    accent: "border-l-primary",
  },
  UNCERTAINTY: {
    label: "Chatbot chưa thể trả lời",
    icon: HelpCircle,
    tone: "bg-warning/20 text-warning-foreground",
    accent: "border-l-warning",
  },
};

const STATUS_META: Record<string, { label: string; tone: string }> = {
  PENDING: { label: "Chờ bác sĩ nhận", tone: "bg-muted text-muted-foreground" },
  ASSIGNED: { label: "Đã có bác sĩ nhận", tone: "bg-secondary text-secondary-foreground" },
  ACTIVE: { label: "Đang trao đổi", tone: "bg-success/15 text-success" },
  RESOLVED: { label: "Đã xử lý xong", tone: "bg-success/15 text-success" },
  ANSWERED: { label: "Đã trả lời", tone: "bg-success/15 text-success" },
  CANCELLED: { label: "Đã huỷ", tone: "bg-muted text-muted-foreground" },
};

const STATUS_FILTERS = [
  { value: "", label: "Đang mở" },
  { value: "PENDING", label: "Chờ nhận" },
  { value: "ASSIGNED", label: "Đã nhận" },
  { value: "ACTIVE", label: "Đang trao đổi" },
  { value: "RESOLVED", label: "Đã xử lý" },
  { value: "ANSWERED", label: "Đã trả lời" },
  { value: "CANCELLED", label: "Đã huỷ" },
];

const SORT_OPTIONS = [
  { value: "priority", label: "Ưu tiên an toàn" },
  { value: "newest", label: "Mới nhất" },
  { value: "oldest", label: "Cũ nhất" },
] as const;

const TYPE_FILTERS = [
  { value: "", label: "Tất cả lý do" },
  { value: "SAFETY", label: "Cần ưu tiên an toàn" },
  { value: "USER_REQUEST", label: "Bệnh nhân yêu cầu" },
  { value: "UNCERTAINTY", label: "Chatbot chưa thể trả lời" },
];

function timeAgo(iso: string): string {
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "Không rõ thời gian";
  const diffMs = Math.max(0, Date.now() - time);
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "Vừa chuyển tới";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return new Date(iso).toLocaleString("vi-VN");
}

function QueueSkeleton() {
  return (
    <div className="space-y-3" aria-label="Đang tải hàng đợi">
      {[0, 1, 2].map((item) => (
        <div key={item} className="surface-card flex gap-4 border-l-4 p-4">
          <Skeleton className="h-10 w-10 shrink-0 rounded-xl" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-4 w-full max-w-2xl" />
            <Skeleton className="h-3 w-32" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DoctorReviewQueuePage() {
  const router = useRouter();
  const { accessToken, user } = useAuth();
  const [items, setItems] = useState<DoctorReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [assignedToMeOnly, setAssignedToMeOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [sortOrder, setSortOrder] = useState<(typeof SORT_OPTIONS)[number]["value"]>("priority");
  const [claimingId, setClaimingId] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);

  const load = useCallback(
    async (silent = false) => {
      if (silent) setRefreshing(true);
      else setLoading(true);
      setError(null);
      try {
        const response = await listDoctorReviewQueue(
          {
            status: statusFilter || undefined,
            handoffType: typeFilter || undefined,
            assignedToMe: assignedToMeOnly,
          },
          accessToken,
        );
        setItems(response.items);
        setLastUpdatedAt(new Date());
      } catch (err) {
        setError(err instanceof Error ? err.message : "Không tải được hàng đợi");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [accessToken, assignedToMeOnly, statusFilter, typeFilter],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("vi-VN");
    const filtered = normalized
      ? items.filter((item) =>
          [item.patientName, item.patientId, item.patientQuestion].some((value) =>
            value.toLocaleLowerCase("vi-VN").includes(normalized),
          ),
        )
      : items;

    return [...filtered].sort((left, right) => {
      if (sortOrder === "priority") {
        const priority = (item: DoctorReviewQueueItem) =>
          item.handoffType === "SAFETY" ? 0 : item.handoffType === "USER_REQUEST" ? 1 : 2;
        const priorityDifference = priority(left) - priority(right);
        if (priorityDifference) return priorityDifference;
      }
      const dateDifference =
        new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime();
      return sortOrder === "oldest" || sortOrder === "priority" ? dateDifference : -dateDifference;
    });
  }, [items, query, sortOrder]);

  async function handleClaim(item: DoctorReviewQueueItem) {
    setClaimingId(item.handoffId);
    try {
      await claimDoctorReview(item.handoffId, accessToken);
      toast.success(`Đã nhận yêu cầu của ${item.patientName}`);
      router.push(`/doctor/reviews/${item.handoffId}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nhận yêu cầu thất bại");
      void load(true);
    } finally {
      setClaimingId(null);
    }
  }

  return (
    <div className="space-y-5">
      <section className="surface-card overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border p-5">
          <h1 className="text-xl font-bold">Hàng đợi tư vấn</h1>
          <Button
            variant="outline"
            onClick={() => void load(true)}
            disabled={loading || refreshing}
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Đang cập nhật" : "Cập nhật"}
          </Button>
        </div>

        <div className="space-y-4 p-4 sm:p-5">
          <div className="flex flex-wrap gap-2" aria-label="Lọc theo trạng thái">
            {STATUS_FILTERS.map((option) => (
              <button
                key={option.value || "open"}
                type="button"
                aria-pressed={statusFilter === option.value}
                onClick={() => setStatusFilter(option.value)}
                className={`rounded-full border px-3 py-1.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  statusFilter === option.value
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_minmax(12rem,auto)_minmax(9rem,auto)_auto]">
            <label className="relative block">
              <span className="sr-only">Tìm bệnh nhân hoặc nội dung câu hỏi</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm tên, mã bệnh nhân hoặc nội dung..."
                className="pl-9"
              />
            </label>

            <label className="grid gap-1">
              <span className="sr-only">Lọc theo lý do chuyển bác sĩ</span>
              <select
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
                className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {TYPE_FILTERS.map((option) => (
                  <option key={option.value || "all"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="grid gap-1">
              <span className="sr-only">Sắp xếp hàng đợi</span>
              <select
                aria-label="Sắp xếp hàng đợi"
                value={sortOrder}
                onChange={(event) =>
                  setSortOrder(event.target.value as (typeof SORT_OPTIONS)[number]["value"])
                }
                className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              aria-pressed={assignedToMeOnly}
              onClick={() => setAssignedToMeOnly((value) => !value)}
              className={`inline-flex h-9 items-center justify-center gap-2 rounded-md border px-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                assignedToMeOnly
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-input bg-background text-muted-foreground hover:bg-muted"
              }`}
            >
              <UserCheck className="h-4 w-4" /> Ca của tôi
            </button>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <p aria-live="polite">
              <span className="font-semibold text-foreground">{visibleItems.length}</span> yêu cầu
              phù hợp
            </p>
            {lastUpdatedAt && <p>Cập nhật lúc {lastUpdatedAt.toLocaleTimeString("vi-VN")}</p>}
          </div>
        </div>
      </section>

      {error && (
        <div
          className="surface-card flex flex-wrap items-center justify-between gap-3 border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
          role="alert"
        >
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            Thử lại
          </Button>
        </div>
      )}

      {!error && loading && <QueueSkeleton />}

      {!error && !loading && visibleItems.length === 0 && (
        <div className="surface-card p-10 text-center">
          <Inbox className="mx-auto h-10 w-10 text-muted-foreground/40" />
          <p className="mt-3 font-semibold">Không có yêu cầu phù hợp</p>
          <p className="mt-1 text-sm text-muted-foreground">Điều chỉnh bộ lọc hoặc từ khoá.</p>
        </div>
      )}

      {!error && !loading && visibleItems.length > 0 && (
        <div className="space-y-3">
          {visibleItems.map((item) => {
            const type = TYPE_META[item.handoffType] ?? TYPE_META.UNCERTAINTY;
            const status = STATUS_META[item.status] ?? {
              label: item.status,
              tone: "bg-muted text-muted-foreground",
            };
            const Icon = type.icon;
            const isMine = user?.doctor_id != null && item.assignedDoctorId === user.doctor_id;
            const assignedToAnother = item.assignedDoctorId != null && !isMine;

            return (
              <article
                key={item.handoffId}
                className={`surface-card border-l-4 p-4 transition-shadow hover:shadow-md sm:p-5 ${type.accent}`}
              >
                <div className="flex items-start gap-3 sm:gap-4">
                  <span
                    className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${type.tone}`}
                  >
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/doctor/reviews/${item.handoffId}`}
                        className="truncate text-base font-bold hover:text-primary hover:underline"
                      >
                        {item.patientName}
                      </Link>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${type.tone}`}
                      >
                        {type.label}
                      </span>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${status.tone}`}
                      >
                        {status.label}
                      </span>
                      {isMine && (
                        <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-bold text-primary">
                          Ca của tôi
                        </span>
                      )}
                    </div>

                    <p className="mt-1 text-xs text-muted-foreground">Mã BN: {item.patientId}</p>
                    <blockquote className="mt-3 line-clamp-3 border-l-2 border-border pl-3 text-sm leading-6 text-foreground">
                      “{item.patientQuestion}”
                    </blockquote>
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1.5">
                        <Clock3 className="h-3.5 w-3.5" /> {timeAgo(item.createdAt)}
                      </span>
                      {assignedToAnother && (
                        <span className="inline-flex items-center gap-1.5">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Bác sĩ khác đã nhận
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="hidden shrink-0 sm:block">
                    {item.status === "PENDING" ? (
                      <Button
                        onClick={() => void handleClaim(item)}
                        disabled={claimingId === item.handoffId}
                      >
                        {claimingId === item.handoffId ? "Đang nhận..." : "Nhận và mở"}
                      </Button>
                    ) : (
                      <Button asChild variant={isMine ? "default" : "outline"}>
                        <Link href={`/doctor/reviews/${item.handoffId}`}>Mở cuộc trao đổi</Link>
                      </Button>
                    )}
                  </div>
                </div>

                <div className="mt-4 sm:hidden">
                  {item.status === "PENDING" ? (
                    <Button
                      className="w-full"
                      onClick={() => void handleClaim(item)}
                      disabled={claimingId === item.handoffId}
                    >
                      {claimingId === item.handoffId ? "Đang nhận..." : "Nhận và mở"}
                    </Button>
                  ) : (
                    <Button asChild className="w-full" variant={isMine ? "default" : "outline"}>
                      <Link href={`/doctor/reviews/${item.handoffId}`}>Mở cuộc trao đổi</Link>
                    </Button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
