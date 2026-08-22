"use client";

import { ChevronLeft, ChevronRight, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
} from "@/components/ui/pagination";
import { getPageItems, scrollToTopOfPage } from "@/lib/pagination";
import { useProto } from "@/lib/proto-store";

// 3 hang x 3 cot o man hinh desktop - vua mot khung hinh, khong phai cuon.
const PAGE_SIZE = 9;

export default function FamilyListPage() {
  const { patients, familyContacts } = useProto();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const withDisplayId = patients.map((p) => ({
    ...p,
    displayId: p.id,
  }));
  const query = q.trim().toLowerCase();
  const list = withDisplayId.filter(
    (p) => p.name.toLowerCase().includes(query) || p.displayId.toLowerCase().includes(query),
  );

  const totalPages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const firstRecord = (currentPage - 1) * PAGE_SIZE;
  const pageItems = list.slice(firstRecord, firstRecord + PAGE_SIZE);

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  const goToPage = (nextPage: number) => {
    setPage(Math.min(Math.max(nextPage, 1), totalPages));
    scrollToTopOfPage();
  };

  return (
    <div className="space-y-5">
      <header className="flex justify-end">
        <Input
          placeholder="Tìm theo tên hoặc ID bệnh nhân…"
          aria-label="Tìm theo tên hoặc ID bệnh nhân"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          className="w-full sm:w-64"
        />
      </header>

      <div id="family-list" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {pageItems.map((p) => {
          const contacts = familyContacts.filter((c) => c.patientId === p.id);
          return (
            <div key={p.id} className="surface-card p-5">
              <p className="font-semibold">{p.name}</p>
              <p className="mt-0.5 text-sm text-muted-foreground">
                ID: {p.displayId} · {p.age} tuổi
              </p>

              <div className="mt-3 space-y-2.5 border-t border-border pt-3">
                {contacts.length === 0 && (
                  <p className="text-sm text-muted-foreground">Chưa có người thân được thêm.</p>
                )}
                {contacts.map((c) => (
                  <div key={c.id} className="flex items-center justify-between gap-2">
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5 truncate text-sm font-medium">
                        <Users className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        {c.name}
                      </span>
                      <span className="ml-5 text-xs text-muted-foreground">{c.relation}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {list.length === 0 && (
          <p className="col-span-full py-10 text-center text-sm text-muted-foreground">
            Không tìm thấy bệnh nhân phù hợp.
          </p>
        )}
      </div>

      {list.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            Hiển thị {firstRecord + 1}–{Math.min(firstRecord + PAGE_SIZE, list.length)} trên{" "}
            {list.length} bệnh nhân
          </p>
          <Pagination
            aria-label="Phân trang danh sách người thân"
            className="mx-0 w-auto justify-start sm:justify-end"
          >
            <PaginationContent>
              <PaginationItem>
                <PaginationLink
                  aria-disabled={currentPage === 1}
                  aria-label="Trang trước"
                  className={
                    currentPage === 1
                      ? "pointer-events-none gap-1 pl-2.5 opacity-50"
                      : "gap-1 pl-2.5"
                  }
                  href="#family-list"
                  size="default"
                  tabIndex={currentPage === 1 ? -1 : undefined}
                  onClick={(event) => {
                    event.preventDefault();
                    goToPage(currentPage - 1);
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
                      href="#family-list"
                      isActive={item === currentPage}
                      onClick={(event) => {
                        event.preventDefault();
                        goToPage(item);
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
                  href="#family-list"
                  size="default"
                  tabIndex={currentPage === totalPages ? -1 : undefined}
                  onClick={(event) => {
                    event.preventDefault();
                    goToPage(currentPage + 1);
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
    </div>
  );
}
