"use client";

import { AlertTriangle, HelpCircle, MessageCircleQuestion, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import {
  claimDoctorReview,
  listDoctorReviewQueue,
  type DoctorReviewQueueItem,
} from "@/lib/doctor-reviews";

// BUILD-44: hang doi tu van bac si - nguon du lieu la DoctorReviewRequest
// (backend/services/doctor_handoff.py), tao boi Safety hoac Answerability
// Gate (BUILD-42/43) - khong tao/doan them logic y te o day.

const TYPE_LABEL: Record<string, string> = {
  SAFETY: "An toàn",
  USER_REQUEST: "Yêu cầu trực tiếp",
  UNCERTAINTY: "Chưa rõ ràng",
};

const TYPE_ICON: Record<string, typeof AlertTriangle> = {
  SAFETY: AlertTriangle,
  USER_REQUEST: MessageCircleQuestion,
  UNCERTAINTY: HelpCircle,
};

const TYPE_TONE: Record<string, string> = {
  SAFETY: "bg-destructive/10 text-destructive",
  USER_REQUEST: "bg-primary/10 text-primary",
  UNCERTAINTY: "bg-warning/25 text-warning-foreground",
};

const STATUS_LABEL: Record<string, string> = {
  PENDING: "Chờ nhận",
  ASSIGNED: "Đã nhận",
  ACTIVE: "Đang trao đổi",
};

const STATUS_TONE: Record<string, string> = {
  PENDING: "bg-muted text-muted-foreground",
  ASSIGNED: "bg-secondary text-secondary-foreground",
  ACTIVE: "bg-success/15 text-success",
};

const STATUS_FILTERS = [
  { value: "", label: "Đang mở (chờ nhận/đã nhận/đang trao đổi)" },
  { value: "PENDING", label: "Chờ nhận" },
  { value: "ASSIGNED", label: "Đã nhận" },
  { value: "ACTIVE", label: "Đang trao đổi" },
  { value: "RESOLVED", label: "Đã xử lý xong" },
];

const TYPE_FILTERS = [
  { value: "", label: "Mọi loại" },
  { value: "SAFETY", label: "An toàn" },
  { value: "USER_REQUEST", label: "Yêu cầu trực tiếp" },
  { value: "UNCERTAINTY", label: "Chưa rõ ràng" },
];

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return new Date(iso).toLocaleString("vi-VN");
}

export default function DoctorReviewQueuePage() {
  const { accessToken, user } = useAuth();
  const [items, setItems] = useState<DoctorReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [assignedToMeOnly, setAssignedToMeOnly] = useState(false);
  const [claimingId, setClaimingId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listDoctorReviewQueue(
      {
        status: statusFilter || undefined,
        handoffType: typeFilter || undefined,
        assignedToMe: assignedToMeOnly,
      },
      accessToken,
    )
      .then((res) => setItems(res.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [accessToken, statusFilter, typeFilter, assignedToMeOnly]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleClaim(item: DoctorReviewQueueItem) {
    setClaimingId(item.handoffId);
    try {
      await claimDoctorReview(item.handoffId, accessToken);
      toast.success(`Đã nhận yêu cầu của ${item.patientName}`);
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Nhận yêu cầu thất bại");
    } finally {
      setClaimingId(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold">Hàng đợi tư vấn bệnh nhân</h1>
          <p className="text-sm text-muted-foreground">
            Các cuộc trò chuyện chatbot đã chuyển cho bác sĩ (an toàn, chưa rõ ràng, hoặc bệnh nhân
            yêu cầu trực tiếp).
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Tải lại
        </Button>
      </div>

      <div className="surface-card flex flex-wrap items-center gap-3 p-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          {STATUS_FILTERS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          {TYPE_FILTERS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={assignedToMeOnly}
            onChange={(e) => setAssignedToMeOnly(e.target.checked)}
          />
          Chỉ yêu cầu tôi đã nhận
        </label>
      </div>

      {error && (
        <div className="surface-card border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {!error && !loading && items.length === 0 && (
        <div className="surface-card p-8 text-center text-sm text-muted-foreground">
          Không có yêu cầu nào phù hợp bộ lọc hiện tại.
        </div>
      )}

      <div className="space-y-2">
        {items.map((item) => {
          const Icon = TYPE_ICON[item.handoffType] ?? HelpCircle;
          const isMine = user?.doctor_id != null && item.assignedDoctorId === user.doctor_id;
          return (
            <div key={item.handoffId} className="surface-card flex items-start gap-3 p-4">
              <span
                className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full ${TYPE_TONE[item.handoffType] ?? ""}`}
              >
                <Icon className="h-[18px] w-[18px]" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/doctor/reviews/${item.handoffId}`}
                    className="truncate font-semibold hover:underline"
                  >
                    {item.patientName}
                  </Link>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${TYPE_TONE[item.handoffType] ?? "bg-muted"}`}
                  >
                    {TYPE_LABEL[item.handoffType] ?? item.handoffType}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_TONE[item.status] ?? "bg-muted text-muted-foreground"}`}
                  >
                    {STATUS_LABEL[item.status] ?? item.status}
                  </span>
                  {isMine && (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
                      Của tôi
                    </span>
                  )}
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                  {item.patientQuestion}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">{timeAgo(item.createdAt)}</p>
              </div>
              <div className="flex shrink-0 flex-col gap-2">
                {item.status === "PENDING" && (
                  <Button
                    size="sm"
                    onClick={() => handleClaim(item)}
                    disabled={claimingId === item.handoffId}
                  >
                    Nhận
                  </Button>
                )}
                {item.status !== "PENDING" && (
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/doctor/reviews/${item.handoffId}`}>Mở</Link>
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
