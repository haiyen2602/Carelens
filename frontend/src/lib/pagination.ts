// Danh sach so trang hien thi tren thanh phan trang, rut gon bang "…" khi
// nhieu trang. Tach ra tu doctor/audit/page.tsx (TASK-010) khi trang thu hai
// (doctor/family) can dung cung logic.

export type PageItem = number | "start-ellipsis" | "end-ellipsis";

/**
 * Cuon len dau sau khi doi trang.
 *
 * Cac nut phan trang deu goi preventDefault() de khong day "#id" vao thanh
 * dia chi - nhung lam vay thi trinh duyet cung khong nhay toi neo do nua, nen
 * doi trang xong van dung o giua danh sach. Ham nay cuon lai bang tay.
 *
 * Trang bac si cuon o window (layout khong co vung cuon rieng - xem
 * doctor/layout.tsx, <main> khong co overflow).
 */
export function scrollToTopOfPage() {
  if (typeof window === "undefined") return;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

export function getPageItems(currentPage: number, totalPages: number): PageItem[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  if (currentPage <= 4) {
    return [1, 2, 3, 4, 5, "end-ellipsis", totalPages];
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
    ];
  }

  return [
    1,
    "start-ellipsis",
    currentPage - 1,
    currentPage,
    currentPage + 1,
    "end-ellipsis",
    totalPages,
  ];
}
