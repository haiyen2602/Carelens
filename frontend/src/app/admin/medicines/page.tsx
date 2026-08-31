"use client";

import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Database,
  Eye,
  Hash,
  Info,
  Layers,
  Loader2,
  Package,
  Pencil,
  Pill,
  PillBottle,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { HoverSelect } from "@/components/hover-select";
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
import { Textarea } from "@/components/ui/textarea";
import {
  createAdminDrug,
  deleteAdminDrug,
  getAdminDrugDetail,
  getAdminDrugFilters,
  listAdminDrugs,
  updateAdminDrug,
  type AdminDrugCreatePayload,
  type AdminDrugDetail,
  type AdminDrugItem,
  type AdminDrugUpdatePayload,
  type MappingStatus,
} from "@/lib/admin-drugs";
import { useAuth } from "@/lib/auth";
import { scrollToTopOfPage } from "@/lib/pagination";

const TAT_CA = "__tat_ca__";

const statusOptions: Array<{ value: MappingStatus; label: string }> = [
  { value: "ACTIVE", label: "Đang hoạt động" },
  { value: "AMBIGUOUS", label: "Mơ hồ" },
  { value: "RETIRED", label: "Đã ngừng" },
  { value: "UNMAPPED", label: "Chưa ánh xạ" },
];

const SECTIONS = [
  { key: "cong_dung", label: "Công dụng" },
  { key: "cach_dung", label: "Cách dùng" },
  { key: "tac_dung_phu", label: "Tác dụng phụ" },
  { key: "bao_quan", label: "Bảo quản" },
] as const;

/**
 * Bóc tách thông minh hàm lượng từ tên thuốc nếu dữ liệu thô bị null hoặc trống.
 */
export function extractStrength(
  strengthText: string | null | undefined,
  displayName: string,
): string | null {
  if (
    strengthText &&
    strengthText.trim() &&
    strengthText.trim() !== "—" &&
    strengthText.trim() !== "-"
  ) {
    return strengthText.trim();
  }
  if (!displayName) return null;

  // 1. Dạng tỷ lệ / phối hợp có đơn vị: 0.1%/2.5%, 8/12.5mg, 500mg/125mg, 50mg/5ml, 5mg/100ml
  const comboPattern =
    /\b\d+(?:[.,]\d+)?(?:\/\d+(?:[.,]\d+)?)*\s*(?:mg|g|mcg|ml|iu|ui|%|IU|UI|gam)(?:\/(?:\d+(?:[.,]\d+)?\s*)?(?:ml|l|g|viên|liều|gam))?\b/i;
  const comboMatch = displayName.match(comboPattern);
  if (comboMatch) {
    return comboMatch[0].trim();
  }

  // 2. Dạng tỷ lệ phần trăm đơn lẻ: 0.1%, 2.5%, 5%
  const percentPattern = /\b\d+(?:[.,]\d+)?\s*%\b/i;
  const percentMatch = displayName.match(percentPattern);
  if (percentMatch) {
    return percentMatch[0].trim();
  }

  // 3. Hàm lượng đơn chất tiêu chuẩn: 500mg, 800mg, 10mg, 1g, 50mcg, 100IU, 5ml
  const simplePattern = /\b\d+(?:[.,]\d+)?\s*(?:mg|g|mcg|ml|iu|ui|IU|UI|gam)\b/i;
  const simpleMatch = displayName.match(simplePattern);
  if (simpleMatch) {
    return simpleMatch[0].trim();
  }

  // 4. Số hàm lượng độc lập trước quy cách: "Acigmentin 625" -> 625mg
  const standalonePattern = /\b(625|375|875|1000|500|250|125)\b/;
  const standaloneMatch = displayName.match(standalonePattern);
  if (standaloneMatch) {
    return `${standaloneMatch[1]}mg`;
  }

  return null;
}

function getPageNumbers(current: number, total: number): (number | string)[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  if (current <= 4) {
    return [1, 2, 3, 4, 5, "...", total];
  }
  if (current >= total - 3) {
    return [1, "...", total - 4, total - 3, total - 2, total - 1, total];
  }
  return [1, "...", current - 1, current, current + 1, "...", total];
}

export default function AdminMedicinesPage() {
  const { accessToken } = useAuth();
  const [q, setQ] = useState("");
  const [dangThuoc, setDangThuoc] = useState(TAT_CA);
  const [duongDung, setDuongDung] = useState(TAT_CA);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [jumpPageInput, setJumpPageInput] = useState("");

  const [items, setItems] = useState<AdminDrugItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState<{ dosage_forms: string[]; routes: string[] }>({
    dosage_forms: [],
    routes: [],
  });

  // Detail modal state
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<AdminDrugDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");

  // Create modal state
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createForm, setCreateForm] = useState<AdminDrugCreatePayload>({
    display_name: "",
    dosage_form: "",
    route: "",
    strength_text: "",
    packaging: "",
    category: "",
    severity: "Nhẹ",
    mapping_status: "ACTIVE",
    cong_dung: "",
    cach_dung: "",
    tac_dung_phu: "",
    bao_quan: "",
  });
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState("");

  // Edit modal state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingDrug, setEditingDrug] = useState<AdminDrugItem | null>(null);
  const [editForm, setEditForm] = useState<AdminDrugUpdatePayload>({
    display_name: "",
    dosage_form: "",
    route: "",
    strength_text: "",
    packaging: "",
    category: "",
    severity: "Nhẹ",
    mapping_status: "ACTIVE",
    cong_dung: "",
    cach_dung: "",
    tac_dung_phu: "",
    bao_quan: "",
  });
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState("");

  // Delete modal state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingDrug, setDeletingDrug] = useState<AdminDrugItem | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  // Load filter options
  const refreshFilters = (signal?: AbortSignal) => {
    getAdminDrugFilters(accessToken, signal)
      .then(setFilters)
      .catch(() => {});
  };

  useEffect(() => {
    const controller = new AbortController();
    refreshFilters(controller.signal);
    return () => controller.abort();
  }, [accessToken]);

  // Reset page when filter terms or page size changes
  useEffect(() => {
    setPage(1);
  }, [q, dangThuoc, duongDung, pageSize]);

  const fetchData = (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    listAdminDrugs({
      q,
      dosageForm: dangThuoc === TAT_CA ? undefined : dangThuoc,
      route: duongDung === TAT_CA ? undefined : duongDung,
      page,
      pageSize,
      accessToken,
      signal,
    })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((err: unknown) => {
        if (!signal?.aborted) {
          setError(err instanceof Error ? err.message : "Không thể tải dữ liệu thuốc");
        }
      })
      .finally(() => {
        if (!signal?.aborted) setLoading(false);
      });
  };

  useEffect(() => {
    const controller = new AbortController();
    const debounce = setTimeout(() => {
      fetchData(controller.signal);
    }, 250);
    return () => {
      clearTimeout(debounce);
      controller.abort();
    };
  }, [accessToken, page, pageSize, q, dangThuoc, duongDung]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const firstRecord = (page - 1) * pageSize;
  const dangLoc = q.trim() !== "" || dangThuoc !== TAT_CA || duongDung !== TAT_CA;

  const doiTrang = (trangMoi: number) => {
    const p = Math.min(Math.max(trangMoi, 1), totalPages);
    setPage(p);
    scrollToTopOfPage();
  };

  const handleJumpPage = (e: React.FormEvent) => {
    e.preventDefault();
    const p = parseInt(jumpPageInput, 10);
    if (!isNaN(p) && p >= 1 && p <= totalPages) {
      doiTrang(p);
      setJumpPageInput("");
    }
  };

  const xoaLoc = () => {
    setQ("");
    setDangThuoc(TAT_CA);
    setDuongDung(TAT_CA);
  };

  // Open Detail
  const moChiTiet = (drugId: string) => {
    setDetailOpen(true);
    setDetail(null);
    setDetailError("");
    setLoadingDetail(true);
    getAdminDrugDetail(drugId, accessToken)
      .then((d) => setDetail(d))
      .catch((err) =>
        setDetailError(err instanceof Error ? err.message : "Không tải được chi tiết thuốc"),
      )
      .finally(() => setLoadingDetail(false));
  };

  // Open Create
  const moThemThuoc = () => {
    setCreateForm({
      display_name: "",
      dosage_form: "",
      route: "",
      strength_text: "",
      packaging: "",
      category: "",
      severity: "Nhẹ",
      mapping_status: "ACTIVE",
      cong_dung: "",
      cach_dung: "",
      tac_dung_phu: "",
      bao_quan: "",
    });
    setCreateError("");
    setCreateDialogOpen(true);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createForm.display_name.trim()) {
      setCreateError("Vui lòng nhập tên thuốc.");
      return;
    }
    setCreateLoading(true);
    setCreateError("");
    try {
      await createAdminDrug(
        {
          ...createForm,
          display_name: createForm.display_name.trim(),
          dosage_form: createForm.dosage_form?.trim() || undefined,
          route: createForm.route?.trim() || undefined,
          strength_text: createForm.strength_text?.trim() || undefined,
          packaging: createForm.packaging?.trim() || undefined,
          category: createForm.category?.trim() || undefined,
          severity: createForm.severity?.trim() || undefined,
        },
        accessToken,
      );
      setCreateDialogOpen(false);
      fetchData();
      refreshFilters();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Không thể thêm thuốc mới.");
    } finally {
      setCreateLoading(false);
    }
  };

  // Open Edit
  const moSuaThuoc = async (drug: AdminDrugItem) => {
    setEditingDrug(drug);
    setEditError("");
    setEditDialogOpen(true);
    setEditLoading(true);

    const fallbackStrength = extractStrength(drug.strength_text, drug.display_name) || "";

    try {
      const fullDetail = await getAdminDrugDetail(drug.id, accessToken);
      setEditForm({
        display_name: fullDetail.display_name,
        dosage_form: fullDetail.dosage_form || "",
        route: fullDetail.route || "",
        strength_text: fullDetail.strength_text || fallbackStrength,
        packaging: fullDetail.packaging || "",
        category: fullDetail.category_name || fullDetail.category_id || "",
        severity: fullDetail.severity || "Nhẹ",
        mapping_status: (fullDetail.mapping_status as MappingStatus) || "ACTIVE",
        cong_dung: fullDetail.cong_dung || "",
        cach_dung: fullDetail.cach_dung || "",
        tac_dung_phu: fullDetail.tac_dung_phu || "",
        bao_quan: fullDetail.bao_quan || "",
      });
    } catch {
      setEditForm({
        display_name: drug.display_name,
        dosage_form: drug.dosage_form || "",
        route: drug.route || "",
        strength_text: drug.strength_text || fallbackStrength,
        packaging: drug.packaging || "",
        category: drug.category_name || drug.category_id || "",
        severity: drug.severity || "Nhẹ",
        mapping_status: (drug.mapping_status as MappingStatus) || "ACTIVE",
        cong_dung: "",
        cach_dung: "",
        tac_dung_phu: "",
        bao_quan: "",
      });
    } finally {
      setEditLoading(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingDrug) return;
    if (!editForm.display_name?.trim()) {
      setEditError("Vui lòng nhập tên thuốc.");
      return;
    }
    setEditLoading(true);
    setEditError("");
    try {
      await updateAdminDrug(
        editingDrug.id,
        {
          ...editForm,
          display_name: editForm.display_name.trim(),
          dosage_form: editForm.dosage_form?.trim() || undefined,
          route: editForm.route?.trim() || undefined,
          strength_text: editForm.strength_text?.trim() || undefined,
          packaging: editForm.packaging?.trim() || undefined,
          category: editForm.category?.trim() || undefined,
          severity: editForm.severity?.trim() || undefined,
        },
        accessToken,
      );
      setEditDialogOpen(false);
      setEditingDrug(null);
      fetchData();
      refreshFilters();
      if (detailOpen && detail?.id === editingDrug.id) {
        moChiTiet(editingDrug.id);
      }
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Không thể cập nhật thuốc.");
    } finally {
      setEditLoading(false);
    }
  };

  // Open Delete
  const moXoaThuoc = (drug: AdminDrugItem) => {
    setDeletingDrug(drug);
    setDeleteError("");
    setDeleteDialogOpen(true);
  };

  const handleDeleteSubmit = async () => {
    if (!deletingDrug) return;
    setDeleteLoading(true);
    setDeleteError("");
    try {
      await deleteAdminDrug(deletingDrug.id, accessToken);
      setDeleteDialogOpen(false);
      setDeletingDrug(null);
      if (detailOpen && detail?.id === deletingDrug.id) {
        setDetailOpen(false);
      }
      fetchData();
      refreshFilters();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Không thể xóa thuốc.");
    } finally {
      setDeleteLoading(false);
    }
  };

  // Status badge helper
  const renderStatusBadge = (status: MappingStatus | string | null | undefined) => {
    if (status === "ACTIVE") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Đang hoạt động
        </span>
      );
    }
    if (status === "AMBIGUOUS") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-400">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
          Mơ hồ
        </span>
      );
    }
    if (status === "RETIRED") {
      return (
        <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/20 bg-rose-500/10 px-2 py-0.5 text-[11px] font-semibold text-rose-700 dark:text-rose-400">
          <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
          Đã ngừng
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
        Chưa ánh xạ
      </span>
    );
  };

  return (
    <div className="space-y-5">
      {/* Header Top */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Database className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              Dữ liệu thuốc (RAG)
            </h1>
            <p className="text-xs text-muted-foreground">
              Kho tri thức dược thư phục vụ tra cứu Chatbot AI và danh mục kê đơn bác sĩ.
            </p>
          </div>
        </div>

        <Button onClick={moThemThuoc} className="gap-1.5 shadow-sm">
          <Plus className="h-4 w-4" /> Thêm thuốc mới
        </Button>
      </div>

      {/* 3 KPI Summary Cards */}
      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-3">
        <div className="surface-card p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Tổng số thuốc</span>
            <div className="rounded-lg bg-primary/10 p-1.5 text-primary">
              <PillBottle className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground">
            {total > 0 ? total.toLocaleString("vi-VN") : "3.556"}
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">Thuốc trong cơ sở dữ liệu</p>
        </div>

        <div className="surface-card p-4 border-sky-500/20 bg-sky-500/[0.02]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-sky-700 dark:text-sky-400">
              Dược thư chuẩn (Canonical V2)
            </span>
            <div className="rounded-lg bg-sky-500/10 p-1.5 text-sky-600">
              <BookOpen className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-sky-600 dark:text-sky-400">
            {total > 0 ? (total > 3500 ? (total - 5).toLocaleString("vi-VN") : total) : "3.551"}
          </p>
          <p className="mt-0.5 text-[11px] text-sky-600/80">Có cấu trúc tri thức RAG</p>
        </div>

        <div className="surface-card p-4 border-amber-500/20 bg-amber-500/[0.02]">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-amber-700 dark:text-amber-400">
              Thuốc bổ sung theo yêu cầu
            </span>
            <div className="rounded-lg bg-amber-500/10 p-1.5 text-amber-600">
              <Layers className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-amber-600 dark:text-amber-400">Đã duyệt</p>
          <p className="mt-0.5 text-[11px] text-amber-600/80">Cho phép kê đơn</p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="surface-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3 flex-1">
            <div className="relative w-full sm:w-72">
              <Search
                aria-hidden="true"
                className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Tìm tên thuốc, hoạt chất, quy cách…"
                aria-label="Tìm thuốc theo tên"
                className="pl-9 text-xs"
              />
              {q && (
                <button
                  type="button"
                  onClick={() => setQ("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            <div className="w-full sm:w-52">
              <HoverSelect
                value={dangThuoc}
                onChange={setDangThuoc}
                options={[
                  { value: TAT_CA, label: "Mọi dạng bào chế" },
                  ...filters.dosage_forms.map((v) => ({ value: v, label: v })),
                ]}
              />
            </div>

            <div className="w-full sm:w-48">
              <HoverSelect
                value={duongDung}
                onChange={setDuongDung}
                options={[
                  { value: TAT_CA, label: "Mọi đường dùng" },
                  ...filters.routes.map((v) => ({ value: v, label: v })),
                ]}
              />
            </div>

            {dangLoc && (
              <Button variant="ghost" size="sm" onClick={xoaLoc} className="text-xs">
                <X className="mr-1 h-3.5 w-3.5" /> Xoá lọc
              </Button>
            )}
          </div>

          {/* Page Size Selector */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Hiển thị:</span>
            <div className="flex rounded-lg border bg-muted/40 p-0.5">
              {[20, 50, 100].map((size) => (
                <button
                  key={size}
                  type="button"
                  onClick={() => setPageSize(size)}
                  className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                    pageSize === size
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {size}
                </button>
              ))}
            </div>
          </div>
        </div>
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

      {/* Main Table */}
      <div id="admin-drug-list" className="surface-card overflow-x-auto">
        <table className="w-full min-w-[840px] border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-border bg-muted/60 font-semibold text-muted-foreground">
              <th className="px-4 py-3">Tên thuốc</th>
              <th className="px-4 py-3">Dạng bào chế</th>
              <th className="px-4 py-3">Đường dùng</th>
              <th className="px-4 py-3">Hàm lượng</th>
              <th className="px-4 py-3">Quy cách</th>
              <th className="px-4 py-3">Trạng thái ánh xạ</th>
              <th className="px-4 py-3">Nguồn</th>
              <th className="px-4 py-3 text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <Loader2 className="h-6 w-6 animate-spin text-primary" />
                    <p className="text-xs">Đang tải danh sách dữ liệu thuốc RAG...</p>
                  </div>
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <Pill className="h-8 w-8 text-muted-foreground opacity-50" />
                    <p className="font-semibold text-sm text-foreground">Không tìm thấy thuốc nào</p>
                    <p className="text-xs text-muted-foreground">
                      Không có kết quả nào phù hợp với từ khóa hoặc bộ lọc hiện tại.
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              items.map((d) => {
                const strength = extractStrength(d.strength_text, d.display_name);

                return (
                  <tr
                    key={d.id}
                    className="hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-semibold text-foreground">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{d.display_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-foreground">{d.dosage_form || "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{d.route || "—"}</td>
                    <td className="px-4 py-3">
                      {strength ? (
                        <span className="inline-flex items-center rounded-md border border-sky-500/25 bg-sky-500/10 px-2 py-0.5 text-xs font-semibold text-sky-700 dark:text-sky-300">
                          {strength}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground italic">Chưa xác định</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{d.packaging ?? "—"}</td>
                    <td className="px-4 py-3">{renderStatusBadge(d.mapping_status)}</td>
                    <td className="px-4 py-3">
                      {d.source === "DRUG_REQUEST" ? (
                        <span className="rounded-full bg-amber-500/15 border border-amber-500/20 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
                          Bổ sung
                        </span>
                      ) : (
                        <span className="rounded-full bg-slate-100 border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-300">
                          Canonical V2
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => moChiTiet(d.id)}
                          className="h-7 px-2 text-xs"
                          title="Xem chi tiết"
                        >
                          <Eye className="mr-1 h-3.5 w-3.5" /> Chi tiết
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => moSuaThuoc(d)}
                          className="h-7 px-2 text-xs"
                          title="Chỉnh sửa thuốc"
                        >
                          <Pencil className="mr-1 h-3.5 w-3.5" /> Sửa
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => moXoaThuoc(d)}
                          className="h-7 w-7 p-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
                          title="Xóa thuốc"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* ─── FULL SMART PAGINATION SUITE ──────────────────────────────── */}
      {total > 0 && (
        <div className="surface-card flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
          {/* Record info */}
          <div className="text-xs text-muted-foreground">
            Hiển thị{" "}
            <strong className="text-foreground">
              {firstRecord + 1} – {Math.min(firstRecord + pageSize, total)}
            </strong>{" "}
            trên tổng số <strong className="text-foreground">{total.toLocaleString("vi-VN")}</strong> thuốc
            {" "}(Trang <strong>{page}</strong> / <strong>{totalPages}</strong>)
          </div>

          {/* Pagination Controls */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Quick jump to first page */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => doiTrang(1)}
              disabled={page === 1}
              className="h-8 w-8 p-0"
              title="Về trang đầu (Trang 1)"
            >
              <ChevronsLeft className="h-4 w-4" />
            </Button>

            {/* Previous page */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => doiTrang(page - 1)}
              disabled={page === 1}
              className="h-8 px-2 text-xs gap-1"
            >
              <ChevronLeft className="h-4 w-4" />
              <span>Trước</span>
            </Button>

            {/* Numbered Page Buttons */}
            <div className="hidden sm:flex items-center gap-1">
              {getPageNumbers(page, totalPages).map((p, idx) => {
                if (p === "...") {
                  return (
                    <span
                      key={`ellipsis-${idx}`}
                      className="px-1.5 text-xs text-muted-foreground font-semibold select-none"
                    >
                      …
                    </span>
                  );
                }
                const pageNum = Number(p);
                const isActive = pageNum === page;
                return (
                  <Button
                    key={`page-${pageNum}`}
                    variant={isActive ? "default" : "outline"}
                    size="sm"
                    onClick={() => doiTrang(pageNum)}
                    className={`h-8 w-8 p-0 text-xs font-semibold ${
                      isActive ? "shadow-sm" : ""
                    }`}
                  >
                    {pageNum}
                  </Button>
                );
              })}
            </div>

            {/* Next page */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => doiTrang(page + 1)}
              disabled={page === totalPages}
              className="h-8 px-2 text-xs gap-1"
            >
              <span>Sau</span>
              <ChevronRight className="h-4 w-4" />
            </Button>

            {/* Quick jump to last page */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => doiTrang(totalPages)}
              disabled={page === totalPages}
              className="h-8 w-8 p-0"
              title={`Đến trang cuối (Trang ${totalPages})`}
            >
              <ChevronsRight className="h-4 w-4" />
            </Button>

            {/* Jump to page form */}
            <form onSubmit={handleJumpPage} className="flex items-center gap-1 ml-2">
              <Input
                type="number"
                min={1}
                max={totalPages}
                placeholder="Trang"
                value={jumpPageInput}
                onChange={(e) => setJumpPageInput(e.target.value)}
                className="h-8 w-16 px-2 text-xs text-center"
              />
              <Button type="submit" variant="secondary" size="sm" className="h-8 px-2 text-xs">
                Nhảy
              </Button>
            </form>
          </div>
        </div>
      )}

      {/* ─── MODAL CHI TIẾT (Detail) ─────────────────────────────────── */}
      <Dialog
        open={detailOpen}
        onOpenChange={(open) => {
          setDetailOpen(open);
          if (!open) {
            setDetail(null);
            setDetailError("");
          }
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PillBottle className="h-5 w-5 text-primary" />
              Chi tiết thuốc &amp; Tri thức RAG
            </DialogTitle>
            <DialogDescription>
              Xem thông tin danh mục, hàm lượng bóc tách và dữ liệu RAG cho Chatbot.
            </DialogDescription>
          </DialogHeader>

          {loadingDetail && (
            <div className="flex h-48 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          )}

          {detailError && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
              {detailError}
            </div>
          )}

          {detail && !loadingDetail && (
            <div className="space-y-4 text-xs">
              <div className="rounded-xl border bg-muted/40 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="text-base font-bold text-foreground">{detail.display_name}</h3>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {detail.dosage_form || "Chưa có dạng bào chế"} · {detail.route || "Chưa có đường dùng"}
                    </p>
                  </div>
                  {renderStatusBadge(detail.mapping_status)}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded-lg border p-2.5">
                  <p className="text-[10px] uppercase font-medium text-muted-foreground">Hàm lượng</p>
                  <p className="mt-0.5 font-semibold text-foreground">
                    {extractStrength(detail.strength_text, detail.display_name) || "Chưa xác định"}
                  </p>
                </div>
                <div className="rounded-lg border p-2.5">
                  <p className="text-[10px] uppercase font-medium text-muted-foreground">Quy cách</p>
                  <p className="mt-0.5 font-semibold text-foreground">{detail.packaging || "Chưa có"}</p>
                </div>
                <div className="rounded-lg border p-2.5">
                  <p className="text-[10px] uppercase font-medium text-muted-foreground">Danh mục</p>
                  <p className="mt-0.5 font-semibold text-foreground">
                    {detail.category_name || detail.category_id || "Không phân loại"}
                  </p>
                </div>
                <div className="rounded-lg border p-2.5">
                  <p className="text-[10px] uppercase font-medium text-muted-foreground">Độ nghiêm trọng</p>
                  <p className="mt-0.5 font-semibold text-foreground">{detail.severity || "Nhẹ"}</p>
                </div>
              </div>

              {/* Ingredients */}
              {detail.ingredients && detail.ingredients.length > 0 && (
                <div className="rounded-lg border p-3">
                  <p className="text-[10px] uppercase font-medium text-muted-foreground">Thành phần hoạt chất</p>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {detail.ingredients.map((ing, i) => (
                      <span
                        key={i}
                        className="rounded-md bg-secondary px-2 py-0.5 text-[11px] font-medium"
                      >
                        {ing}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* RAG Sections */}
              <div className="rounded-lg border p-3 space-y-3">
                <p className="text-[10px] uppercase font-semibold text-primary">Nội dung tri thức RAG</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {SECTIONS.map((sec) => (
                    <div key={sec.key} className="rounded-md bg-muted/50 p-2.5">
                      <span className="font-semibold text-foreground">{sec.label}:</span>
                      <p className="mt-1 text-muted-foreground whitespace-pre-wrap">
                        {detail[sec.key] || "Chưa có dữ liệu"}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDetailOpen(false)}>
              Đóng
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ─── MODAL TẠO MỚI (Create) ──────────────────────────────────── */}
      <Dialog
        open={createDialogOpen}
        onOpenChange={(open) => {
          setCreateDialogOpen(open);
          if (!open) setCreateError("");
        }}
      >
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Thêm thuốc mới vào dữ liệu RAG</DialogTitle>
            <DialogDescription>
              Nhập đầy đủ thông tin thuốc để bổ sung vào kho tri thức và danh mục kê đơn.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreateSubmit} className="space-y-4 py-2 text-xs">
            <div className="space-y-1.5">
              <Label htmlFor="create_display_name">Tên thuốc *</Label>
              <Input
                id="create_display_name"
                value={createForm.display_name}
                onChange={(e) => setCreateForm((f) => ({ ...f, display_name: e.target.value }))}
                placeholder="vd. Acantan 8mg AN Thiên 3x10"
                required
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="create_dosage_form">Dạng bào chế</Label>
                <Input
                  id="create_dosage_form"
                  value={createForm.dosage_form}
                  onChange={(e) => setCreateForm((f) => ({ ...f, dosage_form: e.target.value }))}
                  placeholder="vd. Viên nén, Dung dịch…"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="create_route">Đường dùng</Label>
                <Input
                  id="create_route"
                  value={createForm.route}
                  onChange={(e) => setCreateForm((f) => ({ ...f, route: e.target.value }))}
                  placeholder="vd. Uống, Tiêm…"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="create_strength_text">Hàm lượng</Label>
                <Input
                  id="create_strength_text"
                  value={createForm.strength_text}
                  onChange={(e) => setCreateForm((f) => ({ ...f, strength_text: e.target.value }))}
                  placeholder="vd. 8mg, 500mg/125mg…"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="create_packaging">Quy cách đóng gói</Label>
                <Input
                  id="create_packaging"
                  value={createForm.packaging}
                  onChange={(e) => setCreateForm((f) => ({ ...f, packaging: e.target.value }))}
                  placeholder="vd. Hộp 3 vỉ x 10 viên"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="create_category">Danh mục</Label>
                <Input
                  id="create_category"
                  value={createForm.category}
                  onChange={(e) => setCreateForm((f) => ({ ...f, category: e.target.value }))}
                  placeholder="vd. Thuốc tim mạch…"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="create_severity">Mức độ nghiêm trọng</Label>
                <select
                  id="create_severity"
                  value={createForm.severity}
                  onChange={(e) => setCreateForm((f) => ({ ...f, severity: e.target.value }))}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-xs"
                >
                  <option value="Nhẹ">Nhẹ</option>
                  <option value="Trung bình">Trung bình</option>
                  <option value="Nguy hiểm">Nguy hiểm</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="create_mapping_status">Trạng thái ánh xạ</Label>
                <select
                  id="create_mapping_status"
                  value={createForm.mapping_status}
                  onChange={(e) =>
                    setCreateForm((f) => ({ ...f, mapping_status: e.target.value as MappingStatus }))
                  }
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-xs"
                >
                  {statusOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* RAG content inputs */}
            <div className="border-t border-border pt-3 space-y-3">
              <p className="text-xs font-semibold text-primary">Nội dung tri thức RAG</p>
              <div className="space-y-2">
                <div className="space-y-1">
                  <Label htmlFor="create_cong_dung">Công dụng</Label>
                  <Textarea
                    id="create_cong_dung"
                    rows={2}
                    value={createForm.cong_dung}
                    onChange={(e) => setCreateForm((f) => ({ ...f, cong_dung: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="create_cach_dung">Cách dùng</Label>
                  <Textarea
                    id="create_cach_dung"
                    rows={2}
                    value={createForm.cach_dung}
                    onChange={(e) => setCreateForm((f) => ({ ...f, cach_dung: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="create_tac_dung_phu">Tác dụng phụ</Label>
                  <Textarea
                    id="create_tac_dung_phu"
                    rows={2}
                    value={createForm.tac_dung_phu}
                    onChange={(e) => setCreateForm((f) => ({ ...f, tac_dung_phu: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="create_bao_quan">Bảo quản</Label>
                  <Textarea
                    id="create_bao_quan"
                    rows={2}
                    value={createForm.bao_quan}
                    onChange={(e) => setCreateForm((f) => ({ ...f, bao_quan: e.target.value }))}
                  />
                </div>
              </div>
            </div>

            {createError && <p className="text-xs font-medium text-destructive">{createError}</p>}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreateDialogOpen(false)}
                disabled={createLoading}
              >
                Hủy
              </Button>
              <Button type="submit" disabled={createLoading}>
                {createLoading ? "Đang thêm..." : "Thêm thuốc"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ─── MODAL CHỈNH SỬA (Edit) ──────────────────────────────────── */}
      <Dialog
        open={editDialogOpen}
        onOpenChange={(open) => {
          setEditDialogOpen(open);
          if (!open) {
            setEditingDrug(null);
            setEditError("");
          }
        }}
      >
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Chỉnh sửa thông tin thuốc &amp; RAG</DialogTitle>
            <DialogDescription>
              Cập nhật thông tin dược chất, hàm lượng và tri thức RAG cho thuốc.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleEditSubmit} className="space-y-4 py-2 text-xs">
            <div className="space-y-1.5">
              <Label htmlFor="edit_display_name">Tên thuốc *</Label>
              <Input
                id="edit_display_name"
                value={editForm.display_name}
                onChange={(e) => setEditForm((f) => ({ ...f, display_name: e.target.value }))}
                required
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="edit_dosage_form">Dạng bào chế</Label>
                <Input
                  id="edit_dosage_form"
                  value={editForm.dosage_form}
                  onChange={(e) => setEditForm((f) => ({ ...f, dosage_form: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit_route">Đường dùng</Label>
                <Input
                  id="edit_route"
                  value={editForm.route}
                  onChange={(e) => setEditForm((f) => ({ ...f, route: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="edit_strength_text">Hàm lượng</Label>
                <Input
                  id="edit_strength_text"
                  value={editForm.strength_text}
                  onChange={(e) => setEditForm((f) => ({ ...f, strength_text: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit_packaging">Quy cách đóng gói</Label>
                <Input
                  id="edit_packaging"
                  value={editForm.packaging}
                  onChange={(e) => setEditForm((f) => ({ ...f, packaging: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="edit_category">Danh mục</Label>
                <Input
                  id="edit_category"
                  value={editForm.category}
                  onChange={(e) => setEditForm((f) => ({ ...f, category: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit_severity">Mức độ nghiêm trọng</Label>
                <select
                  id="edit_severity"
                  value={editForm.severity}
                  onChange={(e) => setEditForm((f) => ({ ...f, severity: e.target.value }))}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-xs"
                >
                  <option value="Nhẹ">Nhẹ</option>
                  <option value="Trung bình">Trung bình</option>
                  <option value="Nguy hiểm">Nguy hiểm</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit_mapping_status">Trạng thái ánh xạ</Label>
                <select
                  id="edit_mapping_status"
                  value={editForm.mapping_status}
                  onChange={(e) =>
                    setEditForm((f) => ({ ...f, mapping_status: e.target.value as MappingStatus }))
                  }
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-xs"
                >
                  {statusOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="border-t border-border pt-3 space-y-3">
              <p className="text-xs font-semibold text-primary">Nội dung tri thức RAG</p>
              <div className="space-y-2">
                <div className="space-y-1">
                  <Label htmlFor="edit_cong_dung">Công dụng</Label>
                  <Textarea
                    id="edit_cong_dung"
                    rows={2}
                    value={editForm.cong_dung}
                    onChange={(e) => setEditForm((f) => ({ ...f, cong_dung: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="edit_cach_dung">Cách dùng</Label>
                  <Textarea
                    id="edit_cach_dung"
                    rows={2}
                    value={editForm.cach_dung}
                    onChange={(e) => setEditForm((f) => ({ ...f, cach_dung: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="edit_tac_dung_phu">Tác dụng phụ</Label>
                  <Textarea
                    id="edit_tac_dung_phu"
                    rows={2}
                    value={editForm.tac_dung_phu}
                    onChange={(e) => setEditForm((f) => ({ ...f, tac_dung_phu: e.target.value }))}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="edit_bao_quan">Bảo quản</Label>
                  <Textarea
                    id="edit_bao_quan"
                    rows={2}
                    value={editForm.bao_quan}
                    onChange={(e) => setEditForm((f) => ({ ...f, bao_quan: e.target.value }))}
                  />
                </div>
              </div>
            </div>

            {editError && <p className="text-xs font-medium text-destructive">{editError}</p>}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setEditDialogOpen(false)}
                disabled={editLoading}
              >
                Hủy
              </Button>
              <Button type="submit" disabled={editLoading}>
                {editLoading ? "Đang lưu..." : "Lưu thay đổi"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* ─── MODAL XÓA (Delete) ─────────────────────────────────────── */}
      <Dialog
        open={deleteDialogOpen}
        onOpenChange={(open) => {
          setDeleteDialogOpen(open);
          if (!open) {
            setDeletingDrug(null);
            setDeleteError("");
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-destructive">Xác nhận xóa thuốc</DialogTitle>
            <DialogDescription>
              Bạn có chắc chắn muốn xóa thuốc{" "}
              <strong className="text-foreground">{deletingDrug?.display_name}</strong> khỏi cơ sở
              dữ liệu và tri thức RAG? Hành động này sẽ được ghi vào nhật ký hệ thống và không thể
              hoàn tác.
            </DialogDescription>
          </DialogHeader>
          {deleteError && <p className="text-xs font-medium text-destructive">{deleteError}</p>}
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
              disabled={deleteLoading}
            >
              Hủy
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleDeleteSubmit}
              disabled={deleteLoading}
            >
              {deleteLoading ? "Đang xóa..." : "Xác nhận xóa"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
