"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowUpDown,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  Eye,
  FileText,
  Filter,
  Inbox,
  Info,
  Loader2,
  Pill,
  PillBottle,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Stethoscope,
  X,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import {
  approveDrugRequest,
  listAllDrugRequests,
  rejectDrugRequest,
  type DrugRequest,
  type DrugRequestStatus,
} from "@/lib/drug-requests";

type FilterStatus = "ALL" | DrugRequestStatus;

const QUICK_REJECT_REASONS = [
  "Đã có biệt dược tương đương trong danh mục",
  "Chưa đủ thông tin về dạng bào chế hoặc hàm lượng",
  "Thuốc thuộc danh mục hạn chế sử dụng / cần hội chẩn",
  "Thông tin hoạt chất và đường dùng chưa chuẩn xác",
];

export default function AdminDrugRequestsPage() {
  const { accessToken } = useAuth();
  const [allRequests, setAllRequests] = useState<DrugRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Filters & Sorting
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");

  // Action states
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState<DrugRequest | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);

  // Approve dialog
  const [approveDialogOpen, setApproveDialogOpen] = useState(false);
  const [requestToApprove, setRequestToApprove] = useState<DrugRequest | null>(null);

  // Reject dialog
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [requestToReject, setRequestToReject] = useState<DrugRequest | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const fetchAllData = useCallback(async () => {
    try {
      // Fetch all status groups to calculate KPI counts accurately
      const [pending, approved, rejected] = await Promise.all([
        listAllDrugRequests("PENDING", accessToken),
        listAllDrugRequests("APPROVED", accessToken),
        listAllDrugRequests("REJECTED", accessToken),
      ]);
      setAllRequests([...pending, ...approved, ...rejected]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không tải được danh sách yêu cầu thuốc");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void fetchAllData();
  }, [fetchAllData]);

  const handleRefresh = () => {
    setRefreshing(true);
    void fetchAllData();
  };

  const handleCopy = (text: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    toast.success(`Đã sao chép mã: ${text}`);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // KPI Calculations
  const stats = useMemo(() => {
    const pending = allRequests.filter((r) => r.status === "PENDING").length;
    const approved = allRequests.filter((r) => r.status === "APPROVED").length;
    const rejected = allRequests.filter((r) => r.status === "REJECTED").length;
    return {
      total: allRequests.length,
      pending,
      approved,
      rejected,
    };
  }, [allRequests]);

  // Filtered and Sorted list
  const filteredList = useMemo(() => {
    return allRequests
      .filter((r) => {
        // Status filter
        if (filterStatus !== "ALL" && r.status !== filterStatus) return false;

        // Search query filter
        if (!searchQuery.trim()) return true;
        const q = searchQuery.toLowerCase();
        const matchName = r.ten_thuoc?.toLowerCase().includes(q);
        const matchForm = r.dang_thuoc?.toLowerCase().includes(q);
        const matchRoute = r.duong_dung?.toLowerCase().includes(q);
        const matchDoctor = r.requested_by_doctor_id?.toLowerCase().includes(q);
        const matchApprovedId = r.approved_drug_id?.toLowerCase().includes(q);
        const matchReason = r.ly_do?.toLowerCase().includes(q);

        return matchName || matchForm || matchRoute || matchDoctor || matchApprovedId || matchReason;
      })
      .sort((a, b) => {
        const timeA = new Date(a.created_at).getTime();
        const timeB = new Date(b.created_at).getTime();
        return sortOrder === "newest" ? timeB - timeA : timeA - timeB;
      });
  }, [allRequests, filterStatus, searchQuery, sortOrder]);

  // Actions
  const handleOpenApprove = (row: DrugRequest) => {
    setRequestToApprove(row);
    setApproveDialogOpen(true);
  };

  const handleConfirmApprove = async () => {
    if (!requestToApprove) return;
    setActionLoading(true);
    try {
      const res = await approveDrugRequest(requestToApprove.id, undefined, accessToken);
      toast.success(`Đã phê duyệt thuốc thành công! Mã thuốc mới: ${res.approved_drug_id}`);
      setApproveDialogOpen(false);
      setRequestToApprove(null);
      if (detailDialogOpen) setDetailDialogOpen(false);
      await fetchAllData();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Phê duyệt thuốc thất bại");
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenReject = (row: DrugRequest) => {
    setRequestToReject(row);
    setRejectReason("");
    setRejectDialogOpen(true);
  };

  const handleConfirmReject = async () => {
    if (!requestToReject) return;
    const note = rejectReason.trim();
    if (!note) {
      toast.error("Vui lòng nhập hoặc chọn lý do từ chối.");
      return;
    }
    setActionLoading(true);
    try {
      await rejectDrugRequest(requestToReject.id, note, accessToken);
      toast.success("Đã từ chối yêu cầu bổ sung thuốc.");
      setRejectDialogOpen(false);
      setRequestToReject(null);
      setRejectReason("");
      if (detailDialogOpen) setDetailDialogOpen(false);
      await fetchAllData();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Từ chối yêu cầu thất bại");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <PillBottle className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground">
                Yêu cầu bổ sung thuốc
              </h1>
              <p className="text-xs text-muted-foreground">
                Xem xét, phê duyệt các đề xuất thuốc ngoài danh mục từ bác sĩ điều trị để cho phép kê đơn.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="h-9 gap-1.5 text-xs"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            Làm mới
          </Button>
        </div>
      </div>

      {/* Policy Alert Banner */}
      <div className="relative overflow-hidden rounded-xl border border-primary/25 bg-gradient-to-r from-primary/10 via-primary/5 to-transparent p-4">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/20 text-primary">
            <Info className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-primary">
                Quy chuẩn phê duyệt &amp; Đồng bộ RAG
              </span>
              <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary">
                Kê đơn có hiệu lực ngay
              </span>
            </div>
            <p className="text-xs leading-relaxed text-foreground/90">
              Thuốc sau khi được phê duyệt tại đây sẽ <strong>lập tức xuất hiện trong danh mục cho phép bác sĩ kê đơn</strong>.
              Đối với dữ liệu hỏi đáp và tra cứu tương tác của Chatbot AI (RAG), hệ thống sẽ tiến hành đồng bộ tri thức dược thư đầy đủ trong chu kỳ cập nhật tiếp theo.
            </p>
          </div>
        </div>
      </div>

      {/* 4 KPI Summary Cards */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        {/* Total */}
        <div className="surface-card p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Tổng yêu cầu</span>
            <div className="rounded-lg bg-muted p-1.5 text-muted-foreground">
              <Inbox className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground">{stats.total}</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">Đề xuất thuốc từ bác sĩ</p>
        </div>

        {/* Pending */}
        <div className="surface-card p-4 border-amber-500/30 bg-amber-500/[0.03]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-amber-700 dark:text-amber-400">Chờ phê duyệt</span>
            <div className="rounded-lg bg-amber-500/10 p-1.5 text-amber-600">
              <Clock className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-amber-600 dark:text-amber-400">{stats.pending}</p>
          <p className="mt-0.5 text-[11px] text-amber-600/80 font-medium">
            {stats.pending > 0 ? "⚡ Cần xử lý ngay" : "Đã xử lý hết"}
          </p>
        </div>

        {/* Approved */}
        <div className="surface-card p-4 border-emerald-500/30 bg-emerald-500/[0.03]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-emerald-700 dark:text-emerald-400">Đã phê duyệt</span>
            <div className="rounded-lg bg-emerald-500/10 p-1.5 text-emerald-600">
              <CheckCircle2 className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-emerald-600 dark:text-emerald-400">{stats.approved}</p>
          <p className="mt-0.5 text-[11px] text-emerald-600/80">Cho phép kê đơn</p>
        </div>

        {/* Rejected */}
        <div className="surface-card p-4 border-rose-500/30 bg-rose-500/[0.03]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-rose-700 dark:text-rose-400">Đã từ chối</span>
            <div className="rounded-lg bg-rose-500/10 p-1.5 text-rose-600">
              <XCircle className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-rose-600 dark:text-rose-400">{stats.rejected}</p>
          <p className="mt-0.5 text-[11px] text-rose-600/80">Không đạt tiêu chuẩn</p>
        </div>
      </div>

      {/* Main Container: Controls & Data Table */}
      <div className="surface-card space-y-4 p-5">
        {/* Controls Toolbar */}
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          {/* Status Tabs */}
          <div className="flex flex-wrap items-center gap-1.5 rounded-xl border bg-muted/40 p-1">
            <button
              type="button"
              onClick={() => setFilterStatus("ALL")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                filterStatus === "ALL"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Tất cả
              <span className="rounded-full bg-muted px-1.5 py-0.2 text-[10px] text-muted-foreground">
                {stats.total}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setFilterStatus("PENDING")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                filterStatus === "PENDING"
                  ? "bg-amber-500 text-white shadow-sm"
                  : "text-amber-700 dark:text-amber-400 hover:bg-amber-500/10"
              }`}
            >
              <Clock className="h-3.5 w-3.5" />
              Chờ duyệt
              <span
                className={`rounded-full px-1.5 py-0.2 text-[10px] ${
                  filterStatus === "PENDING" ? "bg-white/20 text-white" : "bg-amber-500/20 text-amber-700 dark:text-amber-300"
                }`}
              >
                {stats.pending}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setFilterStatus("APPROVED")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                filterStatus === "APPROVED"
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "text-emerald-700 dark:text-emerald-400 hover:bg-emerald-500/10"
              }`}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Đã duyệt
              <span
                className={`rounded-full px-1.5 py-0.2 text-[10px] ${
                  filterStatus === "APPROVED" ? "bg-white/20 text-white" : "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300"
                }`}
              >
                {stats.approved}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setFilterStatus("REJECTED")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                filterStatus === "REJECTED"
                  ? "bg-rose-600 text-white shadow-sm"
                  : "text-rose-700 dark:text-rose-400 hover:bg-rose-500/10"
              }`}
            >
              <XCircle className="h-3.5 w-3.5" />
              Đã từ chối
              <span
                className={`rounded-full px-1.5 py-0.2 text-[10px] ${
                  filterStatus === "REJECTED" ? "bg-white/20 text-white" : "bg-rose-500/20 text-rose-700 dark:text-rose-300"
                }`}
              >
                {stats.rejected}
              </span>
            </button>
          </div>

          {/* Search & Sort */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 sm:w-64">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Tìm tên thuốc, bác sĩ, hoạt chất..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-8 w-full rounded-lg border bg-background pl-8 pr-3 text-xs text-foreground focus:border-primary focus:outline-none"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <ArrowUpDown className="h-3.5 w-3.5 shrink-0" />
              <select
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value as any)}
                className="h-8 rounded-lg border bg-background px-2 text-xs text-foreground focus:border-primary focus:outline-none"
              >
                <option value="newest">Mới nhất trước</option>
                <option value="oldest">Cũ nhất trước</option>
              </select>
            </div>
          </div>
        </div>

        {/* Data Table */}
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="py-3 px-3.5 font-semibold">Thuốc đề xuất</th>
                <th className="py-3 px-3.5 font-semibold">Quy cách &amp; Hàm lượng</th>
                <th className="py-3 px-3.5 font-semibold">Bác sĩ đề xuất</th>
                <th className="py-3 px-3.5 font-semibold">Lý do lâm sàng</th>
                <th className="py-3 px-3.5 font-semibold">Trạng thái &amp; Mã cấp</th>
                <th className="py-3 px-3.5 font-semibold text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-muted-foreground">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <Loader2 className="h-6 w-6 animate-spin text-primary" />
                      <p className="text-xs">Đang tải danh sách yêu cầu bổ sung thuốc...</p>
                    </div>
                  </td>
                </tr>
              ) : filteredList.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-muted-foreground">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                        <Pill className="h-6 w-6 opacity-60" />
                      </div>
                      <p className="font-semibold text-sm text-foreground">Không có yêu cầu nào</p>
                      <p className="max-w-md text-xs text-muted-foreground">
                        {filterStatus === "PENDING"
                          ? "Tuyệt vời! Hiện tại không có yêu cầu bổ sung thuốc nào đang chờ phê duyệt."
                          : filterStatus === "APPROVED"
                          ? "Chưa có thuốc nào được phê duyệt trong danh mục này."
                          : filterStatus === "REJECTED"
                          ? "Không có yêu cầu nào bị từ chối."
                          : "Không tìm thấy yêu cầu bổ sung thuốc nào phù hợp với bộ lọc."}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredList.map((row) => {
                  const isPending = row.status === "PENDING";
                  const isApproved = row.status === "APPROVED";
                  const isRejected = row.status === "REJECTED";

                  return (
                    <tr key={row.id} className="hover:bg-muted/30 transition-colors">
                      {/* Drug Name */}
                      <td className="py-3 px-3.5">
                        <div className="flex items-start gap-2">
                          <div
                            className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                              isApproved
                                ? "bg-emerald-500/10 text-emerald-600"
                                : isRejected
                                ? "bg-rose-500/10 text-rose-600"
                                : "bg-amber-500/10 text-amber-600"
                            }`}
                          >
                            <Pill className="h-4 w-4" />
                          </div>
                          <div>
                            <span className="font-semibold text-sm text-foreground">
                              {row.ten_thuoc}
                            </span>
                            <div className="font-mono text-[10px] text-muted-foreground mt-0.5">
                              ID: {row.id.slice(0, 8)}...
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Specs */}
                      <td className="py-3 px-3.5">
                        <div className="space-y-0.5">
                          <span className="inline-flex rounded-md bg-muted px-2 py-0.5 text-[11px] font-medium text-foreground">
                            {row.dang_thuoc} · {row.duong_dung}
                          </span>
                          {row.ham_luong && (
                            <p className="text-[11px] text-muted-foreground">
                              Hàm lượng: <strong>{row.ham_luong}</strong>
                            </p>
                          )}
                          {row.tong_so_luong && (
                            <p className="text-[10px] text-muted-foreground">
                              SL dự kiến: {row.tong_so_luong}
                            </p>
                          )}
                        </div>
                      </td>

                      {/* Doctor */}
                      <td className="py-3 px-3.5">
                        <div className="space-y-0.5">
                          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">
                            <Stethoscope className="h-3 w-3" />
                            {row.requested_by_doctor_id}
                          </span>
                          <p className="text-[10px] text-muted-foreground">
                            {new Date(row.created_at).toLocaleString("vi-VN", {
                              hour: "2-digit",
                              minute: "2-digit",
                              day: "2-digit",
                              month: "2-digit",
                              year: "numeric",
                            })}
                          </p>
                        </div>
                      </td>

                      {/* Reason */}
                      <td className="py-3 px-3.5 max-w-[200px]">
                        {row.ly_do ? (
                          <p className="truncate text-xs text-muted-foreground" title={row.ly_do}>
                            {row.ly_do}
                          </p>
                        ) : (
                          <span className="text-[11px] text-muted-foreground italic">
                            Không có lý do kèm theo
                          </span>
                        )}
                      </td>

                      {/* Status & Drug ID */}
                      <td className="py-3 px-3.5">
                        {isPending ? (
                          <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-400">
                            <Clock className="h-3 w-3" />
                            Chờ phê duyệt
                          </span>
                        ) : isApproved ? (
                          <div className="space-y-1">
                            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">
                              <CheckCircle2 className="h-3 w-3" />
                              Đã phê duyệt
                            </span>
                            {row.approved_drug_id && (
                              <div
                                onClick={(e) => handleCopy(row.approved_drug_id!, e)}
                                className="group/code flex cursor-pointer items-center gap-1 font-mono text-[10px] text-primary hover:underline"
                                title="Mã thuốc trong danh mục (Bấm để sao chép)"
                              >
                                <span>{row.approved_drug_id}</span>
                                {copiedId === row.approved_drug_id ? (
                                  <Check className="h-2.5 w-2.5 text-emerald-600" />
                                ) : (
                                  <Copy className="h-2.5 w-2.5 opacity-60 group-hover/code:opacity-100" />
                                )}
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="space-y-1">
                            <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/20 bg-rose-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-rose-700 dark:text-rose-400">
                              <XCircle className="h-3 w-3" />
                              Đã từ chối
                            </span>
                            {row.review_note && (
                              <p className="truncate text-[10px] text-muted-foreground" title={row.review_note}>
                                {row.review_note}
                              </p>
                            )}
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-3.5 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSelectedRequest(row);
                              setDetailDialogOpen(true);
                            }}
                            className="h-7 px-2 text-xs"
                            title="Xem chi tiết"
                          >
                            <Eye className="h-3.5 w-3.5 mr-1" />
                            Chi tiết
                          </Button>

                          {isPending && (
                            <>
                              <Button
                                size="sm"
                                onClick={() => handleOpenApprove(row)}
                                className="h-7 bg-emerald-600 px-2.5 text-xs text-white hover:bg-emerald-700 shadow-sm"
                              >
                                <Check className="mr-1 h-3.5 w-3.5" />
                                Duyệt
                              </Button>

                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleOpenReject(row)}
                                className="h-7 border-rose-200 px-2.5 text-xs text-rose-600 hover:bg-rose-50 dark:border-rose-800 dark:hover:bg-rose-950"
                              >
                                <X className="mr-1 h-3.5 w-3.5" />
                                Từ chối
                              </Button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── 1. DETAIL DIALOG ─────────────────────────────────────────── */}
      <Dialog open={detailDialogOpen} onOpenChange={setDetailDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PillBottle className="h-5 w-5 text-primary" />
              Chi tiết yêu cầu bổ sung thuốc
            </DialogTitle>
            <DialogDescription>
              Xem xét đầy đủ thông tin dược chất và lý do đề xuất từ bác sĩ điều trị.
            </DialogDescription>
          </DialogHeader>

          {selectedRequest && (
            <div className="space-y-4 py-2 text-xs">
              {/* Header card */}
              <div className="rounded-xl border bg-muted/40 p-3.5 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-base font-bold text-foreground">
                      {selectedRequest.ten_thuoc}
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      {selectedRequest.dang_thuoc} · {selectedRequest.duong_dung}
                    </p>
                  </div>
                  <div>
                    {selectedRequest.status === "PENDING" ? (
                      <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-600 border border-amber-200">
                        Chờ phê duyệt
                      </span>
                    ) : selectedRequest.status === "APPROVED" ? (
                      <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-600 border border-emerald-200">
                        Đã phê duyệt
                      </span>
                    ) : (
                      <span className="rounded-full bg-rose-500/10 px-2.5 py-1 text-xs font-semibold text-rose-600 border border-rose-200">
                        Đã từ chối
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Grid details */}
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border p-2.5">
                  <p className="text-[10px] text-muted-foreground uppercase font-medium">Hàm lượng</p>
                  <p className="font-semibold text-foreground mt-0.5">
                    {selectedRequest.ham_luong || "Không ghi rõ"}
                  </p>
                </div>
                <div className="rounded-lg border p-2.5">
                  <p className="text-[10px] text-muted-foreground uppercase font-medium">Số lượng dự kiến</p>
                  <p className="font-semibold text-foreground mt-0.5">
                    {selectedRequest.tong_so_luong || "Tùy đơn kê"}
                  </p>
                </div>
                <div className="rounded-lg border p-2.5">
                  <p className="text-[10px] text-muted-foreground uppercase font-medium">Bác sĩ đề xuất</p>
                  <p className="font-semibold text-foreground mt-0.5">
                    {selectedRequest.requested_by_doctor_id}
                  </p>
                </div>
                <div className="rounded-lg border p-2.5">
                  <p className="text-[10px] text-muted-foreground uppercase font-medium">Thời gian gửi</p>
                  <p className="font-semibold text-foreground mt-0.5">
                    {new Date(selectedRequest.created_at).toLocaleString("vi-VN")}
                  </p>
                </div>
              </div>

              {/* Doctor reason */}
              <div className="rounded-lg border p-3">
                <p className="text-[10px] text-muted-foreground uppercase font-medium">Lý do lâm sàng của bác sĩ</p>
                <p className="mt-1 text-xs leading-relaxed text-foreground">
                  {selectedRequest.ly_do || "Không có lý do chi tiết kèm theo."}
                </p>
              </div>

              {/* Approval / Rejection Result */}
              {selectedRequest.status === "APPROVED" && selectedRequest.approved_drug_id && (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
                  <p className="text-[10px] text-emerald-700 dark:text-emerald-400 uppercase font-semibold">
                    Mã thuốc được cấp trong danh mục
                  </p>
                  <p className="mt-1 font-mono font-bold text-sm text-emerald-600">
                    {selectedRequest.approved_drug_id}
                  </p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Thuốc này đã có thể kê đơn ngay lập tức trong giao diện Bác sĩ.
                  </p>
                </div>
              )}

              {selectedRequest.status === "REJECTED" && (
                <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-3">
                  <p className="text-[10px] text-rose-700 dark:text-rose-400 uppercase font-semibold">
                    Lý do từ chối
                  </p>
                  <p className="mt-1 text-xs text-rose-600 font-medium">
                    {selectedRequest.review_note || "Không có ghi chú phản hồi."}
                  </p>
                </div>
              )}
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-0">
            {selectedRequest?.status === "PENDING" && (
              <div className="flex w-full items-center justify-between gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleOpenReject(selectedRequest)}
                  className="border-rose-200 text-rose-600 hover:bg-rose-50 dark:border-rose-800"
                >
                  <X className="mr-1 h-3.5 w-3.5" />
                  Từ chối yêu cầu
                </Button>
                <Button
                  size="sm"
                  onClick={() => handleOpenApprove(selectedRequest)}
                  className="bg-emerald-600 text-white hover:bg-emerald-700"
                >
                  <Check className="mr-1 h-3.5 w-3.5" />
                  Phê duyệt thuốc
                </Button>
              </div>
            )}
            {selectedRequest?.status !== "PENDING" && (
              <Button variant="outline" size="sm" onClick={() => setDetailDialogOpen(false)}>
                Đóng
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ─── 2. APPROVE CONFIRMATION DIALOG ──────────────────────────── */}
      <Dialog open={approveDialogOpen} onOpenChange={setApproveDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-emerald-600">
              <CheckCircle2 className="h-5 w-5" />
              Xác nhận phê duyệt thuốc
            </DialogTitle>
            <DialogDescription>
              Thuốc sau khi duyệt sẽ được đưa vào danh mục kê đơn chính thức cho toàn bộ bác sĩ.
            </DialogDescription>
          </DialogHeader>

          {requestToApprove && (
            <div className="space-y-3 py-2 text-xs">
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 space-y-1.5">
                <p className="text-xs font-bold text-foreground">
                  {requestToApprove.ten_thuoc}
                </p>
                <p className="text-muted-foreground">
                  Quy cách: {requestToApprove.dang_thuoc} · {requestToApprove.duong_dung}
                  {requestToApprove.ham_luong ? ` · ${requestToApprove.ham_luong}` : ""}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Bác sĩ đề xuất: <strong>{requestToApprove.requested_by_doctor_id}</strong>
                </p>
              </div>

              <div className="rounded-lg bg-muted/60 p-3 text-[11px] text-muted-foreground leading-relaxed">
                ℹ️ Hệ thống sẽ tự động khởi tạo mã định danh thuốc mới (Mã chuẩn dạng <code className="font-mono text-primary font-bold">DRUG_...</code>) và lưu vào cơ sở dữ liệu.
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setApproveDialogOpen(false)}
              disabled={actionLoading}
            >
              Hủy
            </Button>
            <Button
              size="sm"
              onClick={handleConfirmApprove}
              disabled={actionLoading}
              className="bg-emerald-600 text-white hover:bg-emerald-700"
            >
              {actionLoading ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  Đang duyệt...
                </>
              ) : (
                <>
                  <Check className="mr-1.5 h-3.5 w-3.5" />
                  Xác nhận phê duyệt
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ─── 3. REJECT CONFIRMATION DIALOG ──────────────────────────── */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-600">
              <XCircle className="h-5 w-5" />
              Từ chối yêu cầu bổ sung thuốc
            </DialogTitle>
            <DialogDescription>
              Vui lòng cung cấp lý do từ chối để phản hồi lại cho bác sĩ điều trị.
            </DialogDescription>
          </DialogHeader>

          {requestToReject && (
            <div className="space-y-3 py-2 text-xs">
              <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3">
                <p className="font-bold text-foreground">{requestToReject.ten_thuoc}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Đề xuất bởi: {requestToReject.requested_by_doctor_id}
                </p>
              </div>

              {/* Quick Reason Templates */}
              <div className="space-y-1.5">
                <Label className="text-[11px] text-muted-foreground font-semibold uppercase">
                  Chọn nhanh lý do phổ biến:
                </Label>
                <div className="flex flex-col gap-1">
                  {QUICK_REJECT_REASONS.map((r, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setRejectReason(r)}
                      className={`text-left rounded-lg border px-2.5 py-1.5 text-[11px] transition-colors ${
                        rejectReason === r
                          ? "border-rose-500 bg-rose-500/10 text-rose-700 dark:text-rose-300 font-medium"
                          : "border-border bg-background hover:bg-muted text-muted-foreground"
                      }`}
                    >
                      • {r}
                    </button>
                  ))}
                </div>
              </div>

              {/* Custom Reason Input */}
              <div className="space-y-1">
                <Label htmlFor="reject_reason" className="text-xs font-semibold">
                  Nội dung ghi chú phản hồi cho bác sĩ:
                </Label>
                <Input
                  id="reject_reason"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Nhập lý do cụ thể..."
                  className="text-xs"
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRejectDialogOpen(false)}
              disabled={actionLoading}
            >
              Hủy
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={handleConfirmReject}
              disabled={actionLoading || !rejectReason.trim()}
            >
              {actionLoading ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  Đang xử lý...
                </>
              ) : (
                <>
                  <X className="mr-1.5 h-3.5 w-3.5" />
                  Xác nhận từ chối
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
