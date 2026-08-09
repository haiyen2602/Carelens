"use client";

import { Bot, User } from "lucide-react";

const convo = [
  {
    id: "1",
    from: "ai",
    at: "09:30",
    text: "Chào cô Lan, đã tới giờ uống Paracetamol 500mg sau ăn sáng ạ.",
  },
  { id: "2", from: "user", at: "09:34", text: "Tôi đang ăn, 10 phút nữa uống nhé." },
  {
    id: "3",
    from: "ai",
    at: "09:44",
    text: "Cháu nhắc lại: cô uống 1 viên và chụp ảnh giúp cháu nhé.",
  },
  { id: "4", from: "user", at: "09:47", text: "Uống rồi, ảnh đây." },
  { id: "5", from: "ai", at: "09:47", text: "Đã đối chiếu ảnh khớp phác đồ. Ghi nhận TAKEN." },
];

export default function AiLogPage() {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Log hội thoại AI</h1>
        <p className="text-sm text-muted-foreground">
          Phiên nhắc liều 09:30 — bệnh nhân Nguyễn Thị Lan.
        </p>
      </header>
      <div className="surface-card space-y-4 p-6">
        {convo.map((m) => (
          <div key={m.id} className={`flex gap-3 ${m.from === "user" ? "flex-row-reverse" : ""}`}>
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">
              {m.from === "ai" ? <Bot className="h-4 w-4" /> : <User className="h-4 w-4" />}
            </span>
            <div className="max-w-[75%]">
              <div
                className={`rounded-2xl px-4 py-2.5 text-sm ${
                  m.from === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-foreground"
                }`}
              >
                {m.text}
              </div>
              <p
                className={`mt-1 text-xs text-muted-foreground ${m.from === "user" ? "text-right" : ""}`}
              >
                {m.at}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
