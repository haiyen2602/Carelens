"use client";

import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Eye,
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
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
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
} from "@/components/ui/pagination";
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

const PAGE_SIZE = 20;
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

export default function AdminMedicinesPage() {
  const { accessToken } = useAuth();
  const [q, setQ] = useState("");
  const [dangThuoc, setDangThuoc] = useState(TAT_CA);
  const [duongDung, setDuongDung] = useState(TAT_CA);
  const [page, setPage] = useState(1);

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

  // Reset page when filter terms change
  useEffect(() => {
    setPage(1);
  }, [q, dangThuoc, duongDung]);

  const fetchData = (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    listAdminDrugs({
      q,
      dosageForm: dangThuoc === TAT_CA ? undefined : dangThuoc,
      route: duongDung === TAT_CA ? undefined : duongDung,
      page,
      pageSize: PAGE_SIZE,
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
    }, 300);
    return () => {
      clearTimeout(debounce);
      controller.abort();
    };
  }, [accessToken, page, q, dangThuoc, duongDung]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const firstRecord = (page - 1) * PAGE_SIZE;
  const dangLoc = q.trim() !== "" || dangThuoc !== TAT_CA || duongDung !== TAT_CA;

  const doiTrang = (trangMoi: number) => {
    setPage(Math.min(Math.max(trangMoi, 1), totalPages));
    scrollToTopOfPage();
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

    try {
      const fullDetail = await getAdminDrugDetail(drug.id, accessToken);
      setEditForm({
        display_name: fullDetail.display_name,
        dosage_form: fullDetail.dosage_form || "",
        route: fullDetail.route || "",
        strength_text: fullDetail.strength_text || "",
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
        strength_text: drug.strength_text || "",
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

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative w-full sm:w-72">
            <Search
              aria-hidden="true"
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Gõ tên thuốc, vd. Amlodipine…"
              aria-label="Tìm thuốc theo tên"
              className="pl-9"
            />
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
            <Button variant="ghost" size="sm" onClick={xoaLoc}>
              <X className="mr-1 h-4 w-4" /> Xoá lọc
            </Button>
          )}
        </div>

        <Button onClick={moThemThuoc} className="gap-1.5 shadow-sm">
          <Plus className="h-4 w-4" /> Thêm thuốc mới
        </Button>
      </header>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      {!error && total === 0 && !loading && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Không tìm thấy thuốc nào khớp bộ lọc hiện tại.
        </div>
      )}

      <div id="admin-drug-list" className="surface-card overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/60 text-left text-xs font-semibold text-muted-foreground">
              <th className="px-4 py-3">Tên thuốc</th>
              <th className="px-4 py-3">Dạng bào chế</th>
              <th className="px-4 py-3">Đường dùng</th>
              <th className="px-4 py-3">Hàm lượng</th>
              <th className="px-4 py-3">Quy cách</th>
              <th className="px-4 py-3 text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  <Loader2 className="mx-auto h-5 w-5 animate-spin" aria-label="Đang tải" />
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  Không tìm thấy thuốc nào khớp bộ lọc.
                </td>
              </tr>
            ) : (
              items.map((d) => (
                <tr key={d.id} className="border-b border-border last:border-0 hover:bg-muted/30">
                  <td className="px-4 py-3 font-semibold">{d.display_name}</td>
                  <td className="px-4 py-3">{d.dosage_form || "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{d.route || "—"}</td>
                  <td className="px-4 py-3">{d.strength_text ?? "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{d.packaging ?? "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => moChiTiet(d.id)}
                        title="Xem chi tiết"
                      >
                        <Eye className="mr-1 h-3.5 w-3.5" /> Chi tiết
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => moSuaThuoc(d)}
                        title="Chỉnh sửa thuốc"
                      >
                        <Pencil className="mr-1 h-3.5 w-3.5" /> Sửa
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => moXoaThuoc(d)}
                        className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                        title="Xóa thuốc"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            Hiển thị {firstRecord + 1}–{Math.min(firstRecord + PAGE_SIZE, total)} trên {total} thuốc
          </p>
          <Pagination
            aria-label="Phân trang danh mục thuốc"
            className="mx-0 w-auto justify-start sm:justify-end"
          >
            <PaginationContent>
              <PaginationItem>
                <PaginationLink
                  aria-disabled={page === 1}
                  aria-label="Trang trước"
                  className={
                    page === 1 ? "pointer-events-none gap-1 pl-2.5 opacity-50" : "gap-1 pl-2.5"
                  }
                  href="#admin-drug-list"
                  size="default"
                  tabIndex={page === 1 ? -1 : undefined}
                  onClick={(event) => {
                    event.preventDefault();
                    doiTrang(page - 1);
                  }}
                >
                  <ChevronLeft />
                  <span>Trước</span>
                </PaginationLink>
              </PaginationItem>
              <PaginationItem>
                <span className="px-3 text-sm font-medium">
                  {page} / {totalPages}
                </span>
              </PaginationItem>
              <PaginationItem>
                <PaginationLink
                  aria-disabled={page === totalPages}
                  aria-label="Trang sau"
                  className={
                    page === totalPages
                      ? "pointer-events-none gap-1 pr-2.5 opacity-50"
                      : "gap-1 pr-2.5"
                  }
                  href="#admin-drug-list"
                  size="default"
                  tabIndex={page === totalPages ? -1 : undefined}
                  onClick={(event) => {
                    event.preventDefault();
                    doiTrang(page + 1);
                  }}
                >
                  <span>Sau</span>
                  <ChevronRight />
                </PaginationLink>
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      )}

      {/* Modal Chi tiết (Read) */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="pr-6 text-left text-lg">
              {detail?.display_name ?? "Chi tiết thuốc (RAG)"}
            </DialogTitle>
          </DialogHeader>

          {loadingDetail && <p className="text-sm text-muted-foreground">Đang tải…</p>}
          {detailError && <p className="text-sm font-medium text-destructive">{detailError}</p>}

          {detail && (
            <div className="space-y-5">
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-muted-foreground">Dạng bào chế</dt>
                  <dd className="font-semibold">{detail.dosage_form || "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Đường dùng</dt>
                  <dd className="font-semibold">{detail.route || "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Hàm lượng</dt>
                  <dd className="font-semibold">{detail.strength_text ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Quy cách đóng gói</dt>
                  <dd className="font-semibold">{detail.packaging ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Danh mục</dt>
                  <dd className="font-semibold">{detail.category_name ?? detail.category_id ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Mức độ nghiêm trọng</dt>
                  <dd className="font-semibold">{detail.severity ?? "Nhẹ"}</dd>
                </div>
              </dl>

              {SECTIONS.every((s) => !detail[s.key]) ? (
                <p className="rounded-lg bg-muted/60 p-4 text-sm text-muted-foreground">
                  Thuốc này chưa có phần mô tả chi tiết trong cơ sở tri thức — chỉ có thông tin danh mục ở trên.
                </p>
              ) : (
                SECTIONS.map((s) =>
                  detail[s.key] ? (
                    <div key={s.key}>
                      <p className="text-xs font-bold uppercase text-muted-foreground">{s.label}</p>
                      <p className="mt-1 whitespace-pre-line text-sm leading-relaxed">
                        {detail[s.key]}
                      </p>
                    </div>
                  ) : null,
                )
              )}

              <div className="flex items-center justify-between border-t border-border pt-3">
                <p className="font-mono text-xs text-muted-foreground">
                  ID: {detail.id}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setDetailOpen(false);
                      moSuaThuoc(detail);
                    }}
                  >
                    <Pencil className="mr-1 h-3.5 w-3.5" /> Sửa thuốc này
                  </Button>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Modal Thêm mới (Create) */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Thêm thuốc mới vào cơ sở tri thức (RAG)</DialogTitle>
            <DialogDescription>
              Thêm thuốc và tri thức hướng dẫn sử dụng vào hệ thống. Mọi hành động sẽ được ghi log kiểm toán.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="create_display_name">Tên thuốc <span className="text-destructive">*</span></Label>
              <Input
                id="create_display_name"
                placeholder="vd. Amlodipine 5mg"
                value={createForm.display_name}
                onChange={(e) => setCreateForm((f) => ({ ...f, display_name: e.target.value }))}
                required
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="create_dosage_form">Dạng bào chế</Label>
                <Input
                  id="create_dosage_form"
                  placeholder="vd. Viên nén bao phim"
                  value={createForm.dosage_form}
                  onChange={(e) => setCreateForm((f) => ({ ...f, dosage_form: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create_route">Đường dùng</Label>
                <Input
                  id="create_route"
                  placeholder="vd. Uống, Tiêm..."
                  value={createForm.route}
                  onChange={(e) => setCreateForm((f) => ({ ...f, route: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="create_strength_text">Hàm lượng</Label>
                <Input
                  id="create_strength_text"
                  placeholder="vd. 5mg, 500mg"
                  value={createForm.strength_text}
                  onChange={(e) => setCreateForm((f) => ({ ...f, strength_text: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create_packaging">Quy cách đóng gói</Label>
                <Input
                  id="create_packaging"
                  placeholder="vd. Hộp 3 vỉ x 10 viên"
                  value={createForm.packaging}
                  onChange={(e) => setCreateForm((f) => ({ ...f, packaging: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="create_category">Danh mục</Label>
                <Input
                  id="create_category"
                  placeholder="vd. Tim mạch, Kháng sinh..."
                  value={createForm.category}
                  onChange={(e) => setCreateForm((f) => ({ ...f, category: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create_severity">Mức độ nghiêm trọng</Label>
                <select
                  id="create_severity"
                  value={createForm.severity}
                  onChange={(e) => setCreateForm((f) => ({ ...f, severity: e.target.value }))}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="Nhẹ">Nhẹ</option>
                  <option value="Trung bình">Trung bình</option>
                  <option value="Nguy hiểm">Nguy hiểm</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="create_mapping_status">Trạng thái ánh xạ</Label>
                <select
                  id="create_mapping_status"
                  value={createForm.mapping_status}
                  onChange={(e) =>
                    setCreateForm((f) => ({ ...f, mapping_status: e.target.value as MappingStatus }))
                  }
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {statusOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <h4 className="mb-3 text-sm font-semibold">Nội dung tri thức RAG (Tuỳ chọn)</h4>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="create_cong_dung">Công dụng</Label>
                  <Textarea
                    id="create_cong_dung"
                    rows={2}
                    placeholder="Mô tả công dụng, chỉ định của thuốc..."
                    value={createForm.cong_dung}
                    onChange={(e) => setCreateForm((f) => ({ ...f, cong_dung: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="create_cach_dung">Cách dùng</Label>
                  <Textarea
                    id="create_cach_dung"
                    rows={2}
                    placeholder="Mô tả liều dùng, cách dùng, thời điểm uống..."
                    value={createForm.cach_dung}
                    onChange={(e) => setCreateForm((f) => ({ ...f, cach_dung: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="create_tac_dung_phu">Tác dụng phụ</Label>
                  <Textarea
                    id="create_tac_dung_phu"
                    rows={2}
                    placeholder="Các tác dụng không mong muốn..."
                    value={createForm.tac_dung_phu}
                    onChange={(e) => setCreateForm((f) => ({ ...f, tac_dung_phu: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="create_bao_quan">Bảo quản</Label>
                  <Textarea
                    id="create_bao_quan"
                    rows={2}
                    placeholder="Hướng dẫn điều kiện bảo quản..."
                    value={createForm.bao_quan}
                    onChange={(e) => setCreateForm((f) => ({ ...f, bao_quan: e.target.value }))}
                  />
                </div>
              </div>
            </div>

            {createError && <p className="text-sm font-medium text-destructive">{createError}</p>}
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

      {/* Modal Chỉnh sửa (Update) */}
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
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Chỉnh sửa dữ liệu thuốc (RAG)</DialogTitle>
            <DialogDescription>
              Cập nhật thông tin thuốc và các phần tri thức RAG. Mọi thay đổi sẽ được ghi log kiểm toán.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEditSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit_display_name">Tên thuốc <span className="text-destructive">*</span></Label>
              <Input
                id="edit_display_name"
                value={editForm.display_name}
                onChange={(e) => setEditForm((f) => ({ ...f, display_name: e.target.value }))}
                required
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="edit_dosage_form">Dạng bào chế</Label>
                <Input
                  id="edit_dosage_form"
                  value={editForm.dosage_form}
                  onChange={(e) => setEditForm((f) => ({ ...f, dosage_form: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit_route">Đường dùng</Label>
                <Input
                  id="edit_route"
                  value={editForm.route}
                  onChange={(e) => setEditForm((f) => ({ ...f, route: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="edit_strength_text">Hàm lượng</Label>
                <Input
                  id="edit_strength_text"
                  value={editForm.strength_text}
                  onChange={(e) => setEditForm((f) => ({ ...f, strength_text: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit_packaging">Quy cách đóng gói</Label>
                <Input
                  id="edit_packaging"
                  value={editForm.packaging}
                  onChange={(e) => setEditForm((f) => ({ ...f, packaging: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="edit_category">Danh mục</Label>
                <Input
                  id="edit_category"
                  value={editForm.category}
                  onChange={(e) => setEditForm((f) => ({ ...f, category: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit_severity">Mức độ nghiêm trọng</Label>
                <select
                  id="edit_severity"
                  value={editForm.severity}
                  onChange={(e) => setEditForm((f) => ({ ...f, severity: e.target.value }))}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="Nhẹ">Nhẹ</option>
                  <option value="Trung bình">Trung bình</option>
                  <option value="Nguy hiểm">Nguy hiểm</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit_mapping_status">Trạng thái ánh xạ</Label>
                <select
                  id="edit_mapping_status"
                  value={editForm.mapping_status}
                  onChange={(e) =>
                    setEditForm((f) => ({ ...f, mapping_status: e.target.value as MappingStatus }))
                  }
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {statusOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <h4 className="mb-3 text-sm font-semibold">Nội dung tri thức RAG</h4>
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="edit_cong_dung">Công dụng</Label>
                  <Textarea
                    id="edit_cong_dung"
                    rows={2}
                    value={editForm.cong_dung}
                    onChange={(e) => setEditForm((f) => ({ ...f, cong_dung: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="edit_cach_dung">Cách dùng</Label>
                  <Textarea
                    id="edit_cach_dung"
                    rows={2}
                    value={editForm.cach_dung}
                    onChange={(e) => setEditForm((f) => ({ ...f, cach_dung: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="edit_tac_dung_phu">Tác dụng phụ</Label>
                  <Textarea
                    id="edit_tac_dung_phu"
                    rows={2}
                    value={editForm.tac_dung_phu}
                    onChange={(e) => setEditForm((f) => ({ ...f, tac_dung_phu: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
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

            {editError && <p className="text-sm font-medium text-destructive">{editError}</p>}
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

      {/* Modal Xác nhận Xóa (Delete) */}
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
          {deleteError && <p className="text-sm font-medium text-destructive">{deleteError}</p>}
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
