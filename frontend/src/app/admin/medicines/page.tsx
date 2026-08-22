"use client";

import { AlertCircle, ChevronLeft, ChevronRight, Loader2, Pencil, Search } from "lucide-react";
import { useEffect, useState } from "react";
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
  listAdminDrugs,
  updateAdminDrug,
  type AdminDrugItem,
  type MappingStatus,
} from "@/lib/admin-drugs";

const statusOptions: Array<{ value: MappingStatus; label: string }> = [
  { value: "ACTIVE", label: "Đang hoạt động" },
  { value: "AMBIGUOUS", label: "Mơ hồ" },
  { value: "RETIRED", label: "Đã ngừng" },
  { value: "UNMAPPED", label: "Chưa ánh xạ" },
];

export default function MedicinesPage() {
  const { accessToken } = useAuth();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<MappingStatus | "">("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<AdminDrugItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editingDrug, setEditingDrug] = useState<AdminDrugItem | null>(null);
  const [editForm, setEditForm] = useState<{
    display_name: string;
    dosage_form: string;
    route: string;
    strength_text: string;
    mapping_status: MappingStatus;
  }>({
    display_name: "",
    dosage_form: "",
    route: "",
    strength_text: "",
    mapping_status: "ACTIVE",
  });
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState("");

  const fetchData = (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    listAdminDrugs({
      q: query,
      mappingStatus: status || undefined,
      page,
      accessToken,
      signal,
    })
      .then((result) => {
        setItems(result.items);
        setTotal(result.total);
        setTotalPages(result.total_pages);
      })
      .catch((reason: unknown) => {
        if (!signal?.aborted) {
          setError(reason instanceof Error ? reason.message : "Không thể tải dữ liệu thuốc");
        }
      })
      .finally(() => {
        if (!signal?.aborted) setLoading(false);
      });
  };

  useEffect(() => {
    const controller = new AbortController();
    const debounce = window.setTimeout(() => {
      fetchData(controller.signal);
    }, 300);
    return () => {
      window.clearTimeout(debounce);
      controller.abort();
    };
  }, [accessToken, page, query, status]);

  const changeQuery = (value: string) => {
    setQuery(value);
    setPage(1);
  };
  const changeStatus = (value: string) => {
    setStatus(value as MappingStatus | "");
    setPage(1);
  };

  const openEdit = (drug: AdminDrugItem) => {
    setEditingDrug(drug);
    setEditForm({
      display_name: drug.display_name,
      dosage_form: drug.dosage_form || "",
      route: drug.route || "",
      strength_text: drug.strength_text || "",
      mapping_status: (drug.mapping_status as MappingStatus) || "ACTIVE",
    });
    setEditError("");
    setEditDialogOpen(true);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingDrug) return;
    if (!editForm.display_name.trim()) {
      setEditError("Vui lòng nhập tên thuốc.");
      return;
    }

    setEditLoading(true);
    setEditError("");
    try {
      await updateAdminDrug(
        editingDrug.id,
        {
          display_name: editForm.display_name.trim(),
          dosage_form: editForm.dosage_form.trim() || undefined,
          route: editForm.route.trim() || undefined,
          strength_text: editForm.strength_text.trim() || undefined,
          mapping_status: editForm.mapping_status,
        },
        accessToken,
      );
      setEditDialogOpen(false);
      setEditingDrug(null);
      fetchData();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Không thể lưu cập nhật thuốc.");
    } finally {
      setEditLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm text-muted-foreground">{total} bản ghi thuốc trong cơ sở dữ liệu.</p>
      </header>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative max-w-md flex-1">
          <Search
            aria-hidden="true"
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={query}
            onChange={(event) => changeQuery(event.target.value)}
            placeholder="Tìm theo tên thuốc, hoạt chất..."
            aria-label="Tìm theo tên thuốc hoặc hoạt chất"
            className="pl-9"
          />
        </div>
        <select
          aria-label="Lọc trạng thái ánh xạ"
          value={status}
          onChange={(event) => changeStatus(event.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="">Tất cả trạng thái</option>
          {statusOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
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
      <div className="surface-card overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/60 text-left text-xs font-semibold text-muted-foreground">
              <th className="px-4 py-3">Tên thuốc</th>
              <th className="px-4 py-3">Hoạt chất</th>
              <th className="px-4 py-3">Dạng bào chế</th>
              <th className="px-4 py-3">Đường dùng</th>
              <th className="px-4 py-3">Trạng thái ánh xạ</th>
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
                  Không tìm thấy dữ liệu thuốc phù hợp.
                </td>
              </tr>
            ) : (
              items.map((drug) => (
                <tr key={drug.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-semibold">{drug.display_name}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {drug.ingredients.join(", ") || "-"}
                  </td>
                  <td className="px-4 py-3">{drug.dosage_form || "-"}</td>
                  <td className="px-4 py-3">{drug.route || "-"}</td>
                  <td className="px-4 py-3">{drug.mapping_status || "-"}</td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openEdit(drug)}
                    >
                      <Pencil className="mr-1 h-3.5 w-3.5" /> Sửa
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <nav aria-label="Phân trang" className="flex items-center justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            aria-label="Trang trước"
            disabled={page <= 1}
            onClick={() => setPage((current) => current - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            Trang {page}/{totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            aria-label="Trang sau"
            disabled={page >= totalPages}
            onClick={() => setPage((current) => current + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </nav>
      )}

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
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Chỉnh sửa dữ liệu thuốc</DialogTitle>
            <DialogDescription>
              Cập nhật thông tin thuốc cho cơ sở tri thức RAG.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSaveEdit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit_display_name">Tên thuốc</Label>
              <Input
                id="edit_display_name"
                value={editForm.display_name}
                onChange={(e) => setEditForm((f) => ({ ...f, display_name: e.target.value }))}
              />
            </div>
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
            <div className="space-y-2">
              <Label htmlFor="edit_strength_text">Hàm lượng</Label>
              <Input
                id="edit_strength_text"
                value={editForm.strength_text}
                onChange={(e) => setEditForm((f) => ({ ...f, strength_text: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit_mapping_status">Trạng thái ánh xạ</Label>
              <select
                id="edit_mapping_status"
                value={editForm.mapping_status}
                onChange={(e) =>
                  setEditForm((f) => ({ ...f, mapping_status: e.target.value as MappingStatus }))
                }
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              >
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            {editError && <p className="text-sm font-medium text-destructive">{editError}</p>}
            <DialogFooter>
              <Button type="submit" disabled={editLoading}>
                {editLoading ? "Đang lưu..." : "Lưu thay đổi"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
