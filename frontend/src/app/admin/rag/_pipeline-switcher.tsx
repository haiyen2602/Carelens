"use client";

// Bo chon "Chatbot" / "VLM" o dau trang Giam sat RAG & AI - THEM 2026-08-22.
// 2 route rieng (/admin/rag va /admin/rag/vlm) thay vi 1 trang voi state
// chuyen view: RAG chatbot la du an cua thanh vien khac, tach route giup
// page.tsx cua ho chi bi dung vao DUY NHAT 1 dong (render component nay),
// khong phai viet lai logic fetch/state hien co - giam toi da nguy co xung
// dot code khi 2 nguoi cung sua chung 1 khu vuc.

import Link from "next/link";

const TABS = [
  { key: "chatbot", label: "Chatbot (RAG)", href: "/admin/rag" },
  { key: "vlm", label: "VLM (Đếm thuốc)", href: "/admin/rag/vlm" },
] as const;

export function PipelineSwitcher({ active }: { active: "chatbot" | "vlm" }) {
  return (
    <div className="inline-flex items-center gap-1 rounded-full border bg-muted/40 p-1">
      {TABS.map((tab) => (
        <Link
          key={tab.key}
          href={tab.href}
          className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
            active === tab.key
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}
