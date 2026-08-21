"use client";

import { ChevronLeft, ChevronRight, Eye, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { HoverSelect } from "@/components/hover-select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
} from "@/components/ui/pagination";
import {
  browseDrugs,
  getDrugDetail,
  getDrugFilters,
  type Drug,
  type DrugDetail,
} from "@/lib/drugs";
import { scrollToTopOfPage } from "@/lib/pagination";

const DEBOUNCE_MS = 300;
const PAGE_SIZE = 20;
const TAT_CA = "__tat_ca__";

// 4 doan van ban lay tu drug_chunks. Thuoc chua embed se khong co doan nao.
const SECTIONS = [
  { key: "congDung", label: "Công dụng" },
  { key: "cachDung", label: "Cách dùng" },
  { key: "tacDungPhu", label: "Tác dụng phụ" },
  { key: "baoQuan", label: "Bảo quản" },
] as const;

export default function DrugLookupPage() {
  const [q, setQ] = useState("");
  const [dangThuoc, setDangThuoc] = useState(TAT_CA);
  const [duongDung, setDuongDung] = useState(TAT_CA);
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<Drug[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [filters, setFilters] = useState<{ dangThuoc: string[]; duongDung: string[] }>({
    dangThuoc: [],
    duongDung: [],
  });

  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DrugDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getDrugFilters(controller.signal)
      .then(setFilters)
      .catch(() => {
        // Bo loc hong khong lam hong ca trang - danh sach van tra cuu duoc,
        // chi la khong co dropdown.
      });
    return () => controller.abort();
  }, []);

  // Doi tu khoa/bo loc -> ve trang 1, neu khong se dung o mot trang khong con
  // ton tai sau khi loc.
  useEffect(() => {
    setPage(1);
  }, [q, dangThuoc, duongDung]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const hen = setTimeout(() => {
      browseDrugs(
        {
          q,
          dangThuoc: dangThuoc === TAT_CA ? undefined : dangThuoc,
          duongDung: duongDung === TAT_CA ? undefined : duongDung,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
        },
        controller.signal,
      )
        .then((kq) => {
          setItems(kq.items);
          setTotal(kq.total);
          setError("");
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          setItems([]);
          setTotal(0);
          setError(err instanceof Error ? err.message : "Tra cứu thất bại");
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(hen);
      controller.abort();
    };
  }, [q, dangThuoc, duongDung, page]);

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

  const moChiTiet = (drugId: string) => {
    setOpenId(drugId);
    setDetail(null);
    setDetailError("");
    setLoadingDetail(true);
    getDrugDetail(drugId)
      .then((d) => {
        if (d === null) setDetailError("Thuốc không có trong danh mục.");
        else setDetail(d);
      })
      .catch((err) =>
        setDetailError(err instanceof Error ? err.message : "Không tải được chi tiết thuốc"),
      )
      .finally(() => setLoadingDetail(false));
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center gap-3">
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
              ...filters.dangThuoc.map((v) => ({ value: v, label: v })),
            ]}
          />
        </div>

        <div className="w-full sm:w-48">
          <HoverSelect
            value={duongDung}
            onChange={setDuongDung}
            options={[
              { value: TAT_CA, label: "Mọi đường dùng" },
              ...filters.duongDung.map((v) => ({ value: v, label: v })),
            ]}
          />
        </div>

        {dangLoc && (
          <Button variant="ghost" size="sm" onClick={xoaLoc}>
            <X className="mr-1 h-4 w-4" /> Xoá lọc
          </Button>
        )}
      </header>

      {error && <p className="text-sm font-medium text-destructive">{error}</p>}

      {!error && total === 0 && !loading && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Không tìm thấy thuốc nào khớp bộ lọc hiện tại.
        </div>
      )}

      {items.length > 0 && (
        <div id="drug-list" className="surface-card overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/60 text-left text-xs font-semibold text-muted-foreground">
                <th className="px-4 py-3">Tên thuốc</th>
                <th className="px-4 py-3">Dạng bào chế</th>
                <th className="px-4 py-3">Đường dùng</th>
                <th className="px-4 py-3">Hàm lượng</th>
                <th className="px-4 py-3">Quy cách</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.drugId} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-semibold">{d.tenThuoc}</td>
                  <td className="px-4 py-3">{d.dangThuoc}</td>
                  <td className="px-4 py-3 text-muted-foreground">{d.duongDung}</td>
                  <td className="px-4 py-3">{d.hamLuong ?? "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{d.tongSoLuong ?? "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <Button variant="outline" size="sm" onClick={() => moChiTiet(d.drugId)}>
                      <Eye className="mr-1 h-4 w-4" /> Chi tiết
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

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
                  href="#drug-list"
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
                  href="#drug-list"
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

      <Dialog open={openId !== null} onOpenChange={(open) => !open && setOpenId(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="pr-6 text-left text-lg">
              {detail?.tenThuoc ?? "Chi tiết thuốc"}
            </DialogTitle>
          </DialogHeader>

          {loadingDetail && <p className="text-sm text-muted-foreground">Đang tải…</p>}
          {detailError && <p className="text-sm font-medium text-destructive">{detailError}</p>}

          {detail && (
            <div className="space-y-5">
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-muted-foreground">Dạng bào chế</dt>
                  <dd className="font-semibold">{detail.dangThuoc}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Đường dùng</dt>
                  <dd className="font-semibold">{detail.duongDung}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Hàm lượng</dt>
                  <dd className="font-semibold">{detail.hamLuong ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Quy cách đóng gói</dt>
                  <dd className="font-semibold">{detail.tongSoLuong ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Danh mục</dt>
                  <dd className="font-semibold">{detail.danhMuc ?? "—"}</dd>
                </div>
              </dl>

              {SECTIONS.every((s) => !detail[s.key]) ? (
                <p className="rounded-lg bg-muted/60 p-4 text-sm text-muted-foreground">
                  Thuốc này chưa có phần mô tả chi tiết trong cơ sở tri thức — chỉ có thông tin danh
                  mục ở trên.
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

              <p className="border-t border-border pt-3 font-mono text-xs text-muted-foreground">
                ID: {detail.drugId}
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
