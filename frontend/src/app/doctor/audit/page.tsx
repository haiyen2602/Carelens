"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, ChevronLeft, ChevronRight, MessageCircle, Search, UserRound } from "lucide-react";

import { Input } from "@/components/ui/input";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
} from "@/components/ui/pagination";
import { useAuth } from "@/lib/auth";
import { listMyActions, type MyAction } from "@/lib/audit";
import { getPageItems } from "@/lib/pagination";
import { useProto } from "@/lib/proto-store";
import { boDau } from "@/lib/text";

const PAGE_SIZE = 10;
const DEBOUNCE_MS = 300;

const TABS = [
  { key: "actions", label: "Thao tác của tôi" },
  { key: "conversations", label: "Hội thoại AI" },
] as const;
type Tab = (typeof TABS)[number]["key"];

function ngayGioHienThi(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Thanh phan trang dung chung cho ca hai tab - truoc day khoi nay bi chep
 * nguyen si o doctor/audit va doctor/family, sua mot ben la lech ben kia. */
function ThanhPhanTrang({
  currentPage,
  totalPages,
  onGoToPage,
  anchorId,
  label,
}: {
  currentPage: number;
  totalPages: number;
  onGoToPage: (page: number) => void;
  anchorId: string;
  label: string;
}) {
  return (
    <Pagination aria-label={label} className="mx-0 w-auto justify-start sm:justify-end">
      <PaginationContent>
        <PaginationItem>
          <PaginationLink
            aria-disabled={currentPage === 1}
            aria-label="Trang trước"
            className={
              currentPage === 1 ? "pointer-events-none gap-1 pl-2.5 opacity-50" : "gap-1 pl-2.5"
            }
            href={`#${anchorId}`}
            size="default"
            tabIndex={currentPage === 1 ? -1 : undefined}
            onClick={(event) => {
              event.preventDefault();
              onGoToPage(currentPage - 1);
            }}
          >
            <ChevronLeft />
            <span>Trước</span>
          </PaginationLink>
        </PaginationItem>
        {getPageItems(currentPage, totalPages).map((item) =>
          typeof item === "number" ? (
            <PaginationItem key={item}>
              <PaginationLink
                href={`#${anchorId}`}
                isActive={item === currentPage}
                onClick={(event) => {
                  event.preventDefault();
                  onGoToPage(item);
                }}
              >
                {item}
              </PaginationLink>
            </PaginationItem>
          ) : (
            <PaginationItem key={item}>
              <PaginationEllipsis />
            </PaginationItem>
          ),
        )}
        <PaginationItem>
          <PaginationLink
            aria-disabled={currentPage === totalPages}
            aria-label="Trang sau"
            className={
              currentPage === totalPages
                ? "pointer-events-none gap-1 pr-2.5 opacity-50"
                : "gap-1 pr-2.5"
            }
            href={`#${anchorId}`}
            size="default"
            tabIndex={currentPage === totalPages ? -1 : undefined}
            onClick={(event) => {
              event.preventDefault();
              onGoToPage(currentPage + 1);
            }}
          >
            <span>Sau</span>
            <ChevronRight />
          </PaginationLink>
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  );
}

/** Thao tac cua CHINH bac si dang dang nhap - backend loc theo actor_id lay
 * tu JWT, khong nhan tu query param (xem backend/api/audit_routes.py). Phan
 * trang o day do SERVER lam, khac tab hoi thoai ben duoi cat tu mang co san. */
function TabThaoTac() {
  const { accessToken } = useAuth();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<MyAction[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loi, setLoi] = useState<string | null>(null);

  const goToPage = useCallback((nextPage: number) => {
    setPage(Math.max(nextPage, 1));
    document.getElementById("my-actions")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  useEffect(() => {
    if (!accessToken) return;
    let huy = false;
    const timer = setTimeout(() => {
      setLoading(true);
      listMyActions(accessToken, { q, page, pageSize: PAGE_SIZE })
        .then((data) => {
          if (huy) return;
          setItems(data.items);
          setTotal(data.total);
          setTotalPages(Math.max(1, data.totalPages));
          setLoi(null);
        })
        .catch((err: unknown) => {
          if (huy) return;
          setLoi(err instanceof Error ? err.message : "Không tải được nhật ký thao tác.");
        })
        .finally(() => {
          if (!huy) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      huy = true;
      clearTimeout(timer);
    };
  }, [accessToken, q, page]);

  // Go tu khoa moi thi ve trang 1 - giu nguyen trang 5 khi ket qua chi con 2
  // trang se hien danh sach rong ma khong ro tai sao.
  useEffect(() => {
    setPage(1);
  }, [q]);

  const firstRecord = (page - 1) * PAGE_SIZE;

  return (
    <div className="space-y-6">
      <div className="relative sm:max-w-sm">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Tìm theo thao tác hoặc bệnh nhân…"
          aria-label="Tìm theo thao tác hoặc bệnh nhân"
          className="pl-9"
        />
      </div>

      <div id="my-actions" className="surface-card divide-y divide-border">
        {loading && items.length === 0 && (
          <p className="p-8 text-center text-sm text-muted-foreground">Đang tải…</p>
        )}
        {loi && <p className="p-8 text-center text-sm text-destructive">{loi}</p>}
        {!loading && !loi && items.length === 0 && (
          <p className="p-8 text-center text-sm text-muted-foreground">
            {q.trim()
              ? "Không có thao tác nào khớp từ khoá."
              : "Bạn chưa thực hiện thao tác nào được ghi nhận."}
          </p>
        )}
        {items.map((a) => (
          <div key={a.id} className="flex flex-wrap gap-x-4 gap-y-1 p-4">
            <span className="w-32 shrink-0 font-mono text-sm text-muted-foreground">
              {ngayGioHienThi(a.createdAt)}
            </span>
            <div className="min-w-0">
              <p className="font-semibold">{a.action}</p>
              {a.target && <p className="text-sm text-muted-foreground">{a.target}</p>}
            </div>
          </div>
        ))}
      </div>

      {total > 0 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            Hiển thị {firstRecord + 1}–{Math.min(firstRecord + PAGE_SIZE, total)} trên {total} thao
            tác
          </p>
          <ThanhPhanTrang
            currentPage={Math.min(page, totalPages)}
            totalPages={totalPages}
            onGoToPage={goToPage}
            anchorId="my-actions"
            label="Phân trang nhật ký thao tác"
          />
        </div>
      )}
    </div>
  );
}

/** Hoi thoai AI cua benh nhan - noi dung cu cua trang nay, giu lai vi day la
 * ban ghi kiem chung cau tra loi ma tro ly da noi voi benh nhan.
 *
 * Truoc 2026-08-23 moi luot hien thanh 3 dong chu chay ngang nhau (cau hoi,
 * cau tra loi, ma benh nhan tho) - khong phan biet duoc AI dang tra loi hay
 * benh nhan dang hoi, va ma benh nhan dang la chuoi ky tu vo nghia voi nguoi
 * doc. Gio dung dang hoi-dap that, kem ten benh nhan tra tu danh sach. */
function TabHoiThoai() {
  const { audit, patients } = useProto();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const tenBenhNhan = useMemo(() => new Map(patients.map((p) => [p.id, p.name])), [patients]);

  const list = useMemo(() => {
    const tuKhoa = boDau(q.trim());
    if (!tuKhoa) return audit;
    return audit.filter((a) => {
      const ten = tenBenhNhan.get(a.patientId) ?? "";
      return boDau(
        `${ten} ${a.patientId} ${a.utterance} ${a.finalResponse ?? ""}`,
      ).includes(tuKhoa);
    });
  }, [audit, q, tenBenhNhan]);

  const totalPages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const firstRecord = (currentPage - 1) * PAGE_SIZE;
  const auditOnPage = list.slice(firstRecord, firstRecord + PAGE_SIZE);

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  useEffect(() => {
    setPage(1);
  }, [q]);

  const goToPage = (nextPage: number) => {
    setPage(Math.min(Math.max(nextPage, 1), totalPages));
    document
      .getElementById("audit-log-list")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="space-y-6">
      <div className="relative sm:max-w-sm">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Tìm theo bệnh nhân hoặc nội dung…"
          aria-label="Tìm theo bệnh nhân hoặc nội dung"
          className="pl-9"
        />
      </div>

      <div id="audit-log-list" className="space-y-3">
        {auditOnPage.map((a) => {
          const ten = tenBenhNhan.get(a.patientId);
          return (
            <article key={a.id} className="surface-card overflow-hidden">
              <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-border bg-muted/35 px-4 py-2.5">
                <span className="flex min-w-0 items-center gap-2 text-sm">
                  <UserRound className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="truncate font-semibold">{ten ?? "Bệnh nhân chưa rõ tên"}</span>
                  <span className="truncate font-mono text-xs text-muted-foreground">
                    {a.patientId}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-xs text-muted-foreground">
                  {ngayGioHienThi(a.createdAt)}
                </span>
              </header>

              <div className="space-y-3 p-4">
                <div className="flex gap-3">
                  <MessageCircle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                      Bệnh nhân hỏi
                    </p>
                    <p className="mt-0.5 font-medium">{a.utterance}</p>
                  </div>
                </div>

                {/* Vien trai + nen nhat de tach hai luot noi - khong dung mau
                    canh bao o day, day la hoi thoai binh thuong chu khong phai
                    su co can chu y. */}
                <div className="flex gap-3 rounded-lg border-l-2 border-primary/40 bg-primary/[0.04] p-3">
                  <Bot className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <div className="min-w-0">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                      Trợ lý trả lời
                    </p>
                    <p className="mt-0.5 text-sm">
                      {a.finalResponse ?? (
                        <span className="italic text-muted-foreground">
                          Chưa ghi nhận câu trả lời cho lượt hỏi này.
                        </span>
                      )}
                    </p>
                  </div>
                </div>
              </div>
            </article>
          );
        })}
        {list.length === 0 && (
          <p className="surface-card p-8 text-center text-sm text-muted-foreground">
            {q.trim() ? "Không có hội thoại nào khớp từ khoá." : "Chưa có bản ghi nào."}
          </p>
        )}
      </div>
      {list.length > 0 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            Hiển thị {firstRecord + 1}–{Math.min(firstRecord + PAGE_SIZE, list.length)} trên{" "}
            {list.length} bản ghi
          </p>
          <ThanhPhanTrang
            currentPage={currentPage}
            totalPages={totalPages}
            onGoToPage={goToPage}
            anchorId="audit-log-list"
            label="Phân trang nhật ký hội thoại"
          />
        </div>
      )}
    </div>
  );
}

export default function AuditPage() {
  const [tab, setTab] = useState<Tab>("actions");

  return (
    <div className="space-y-6">
      <div role="tablist" className="flex gap-6 border-b border-border text-sm">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 pb-2.5 font-medium transition-colors ${
              tab === t.key
                ? "border-primary font-semibold text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "actions" ? <TabThaoTac /> : <TabHoiThoai />}
    </div>
  );
}
