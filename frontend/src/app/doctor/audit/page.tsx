"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
} from "@/components/ui/pagination";
import { useProto } from "@/lib/proto-store";

const PAGE_SIZE = 10;

function getPageItems(currentPage: number, totalPages: number) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  if (currentPage <= 4) {
    return [1, 2, 3, 4, 5, "end-ellipsis", totalPages] as const;
  }

  if (currentPage >= totalPages - 3) {
    return [
      1,
      "start-ellipsis",
      totalPages - 4,
      totalPages - 3,
      totalPages - 2,
      totalPages - 1,
      totalPages,
    ] as const;
  }

  return [
    1,
    "start-ellipsis",
    currentPage - 1,
    currentPage,
    currentPage + 1,
    "end-ellipsis",
    totalPages,
  ] as const;
}

export default function AuditPage() {
  const { audit } = useProto();
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(audit.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const firstRecord = (currentPage - 1) * PAGE_SIZE;
  const auditOnPage = audit.slice(firstRecord, firstRecord + PAGE_SIZE);

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  const goToPage = (nextPage: number) => {
    setPage(Math.min(Math.max(nextPage, 1), totalPages));
    document
      .getElementById("audit-log-list")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Audit log</h1>
        <p className="text-sm text-muted-foreground">
          {audit.length} bản ghi hội thoại AI — mỗi bản ghi là một lượt hỏi/đáp giữa bệnh nhân và
          trợ lý AI.
        </p>
      </header>
      <div id="audit-log-list" className="surface-card divide-y divide-border">
        {auditOnPage.map((a) => (
          <div key={a.id} className="flex gap-4 p-4">
            <span className="w-14 shrink-0 font-mono text-sm text-muted-foreground">{a.at}</span>
            <div className="min-w-0">
              <p className="font-semibold">{a.utterance}</p>
              {a.finalResponse && (
                <p className="text-sm text-muted-foreground">{a.finalResponse}</p>
              )}
              <p className="mt-0.5 text-xs text-muted-foreground">Bệnh nhân: {a.patientId}</p>
            </div>
          </div>
        ))}
        {audit.length === 0 && (
          <p className="p-8 text-center text-sm text-muted-foreground">Chưa có bản ghi nào.</p>
        )}
      </div>
      {audit.length > 0 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            Hiển thị {firstRecord + 1}–{Math.min(firstRecord + PAGE_SIZE, audit.length)} trên{" "}
            {audit.length} bản ghi
          </p>
          <Pagination
            aria-label="Phân trang nhật ký hội thoại"
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
                  href="#audit-log-list"
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
                      href="#audit-log-list"
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
                  href="#audit-log-list"
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
