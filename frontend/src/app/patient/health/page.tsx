"use client";

import { useState } from "react";
import { AlertTriangle, Smile, ThumbsUp } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useProto, type AlertLevel } from "@/lib/proto-store";

export default function HealthPage() {
  const { reportHealth, setEmergency, healthLog } = useProto();
  const [mode, setMode] = useState<"ask" | "form" | "done">("ask");
  const [text, setText] = useState("");
  const [level, setLevel] = useState<AlertLevel>("low");

  const submit = () => {
    reportHealth(text || "Không mô tả chi tiết", level);
    if (level === "high") {
      setEmergency(true);
    } else {
      toast(
        level === "mid" ? "Đã báo người thân và lưu log vấn đề" : "Đã ghi nhật ký, theo dõi 48h",
      );
    }
    setMode("done");
    setText("");
  };

  return (
    <div className="space-y-4">
      {mode === "ask" && (
        <section className="surface-card p-5 text-center">
          <Smile className="mx-auto h-10 w-10 text-primary" />
          <h1 className="mt-3 text-xl font-extrabold">Hôm nay bạn thấy thế nào?</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Câu trả lời giúp bác sĩ và người thân theo dõi tình trạng của bạn.
          </p>
          <div className="mt-5 space-y-3">
            <Button
              className="w-full"
              size="lg"
              onClick={() => {
                reportHealth("Bình thường", "low");
                toast.success("Đã ghi nhận: bình thường");
                setMode("done");
              }}
            >
              <ThumbsUp className="mr-1 h-4 w-4" /> Bình thường
            </Button>
            <Button variant="outline" className="w-full" size="lg" onClick={() => setMode("form")}>
              <AlertTriangle className="mr-1 h-4 w-4" /> Không ổn
            </Button>
          </div>
        </section>
      )}

      {mode === "form" && (
        <section className="surface-card space-y-4 p-5">
          <div>
            <h1 className="text-lg font-extrabold">Nhập vấn đề sức khỏe</h1>
            <p className="text-sm text-muted-foreground">
              AI sẽ phân loại mức độ trước khi gửi đi.
            </p>
          </div>
          <Textarea
            rows={4}
            placeholder="Ví dụ: chóng mặt, buồn nôn sau khi uống thuốc…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase text-muted-foreground">
              AI đánh giá mức độ (chọn để mô phỏng)
            </p>
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  ["low", "Nhẹ"],
                  ["mid", "Trung bình"],
                  ["high", "Nghiêm trọng"],
                ] as [AlertLevel, string][]
              ).map(([v, label]) => (
                <button
                  key={v}
                  onClick={() => setLevel(v)}
                  className={`rounded-lg border p-2.5 text-sm font-semibold transition-colors ${
                    level === v
                      ? "border-primary bg-accent text-accent-foreground"
                      : "border-border"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">
            {level === "low" && "→ Ghi nhật ký, theo dõi 48h."}
            {level === "mid" && "→ Báo người thân và lưu log vấn đề."}
            {level === "high" &&
              "→ Overlay cấp cứu, hướng dẫn gọi 115 + push người thân và bác sĩ."}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Button variant="outline" onClick={() => setMode("ask")}>
              Quay lại
            </Button>
            <Button onClick={submit}>Gửi</Button>
          </div>
        </section>
      )}

      {mode === "done" && (
        <section className="surface-card p-5 text-center">
          <h1 className="text-lg font-extrabold">Đã ghi nhận</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Cảm ơn bạn. Hệ thống sẽ tiếp tục theo dõi và nhắc liều tiếp theo.
          </p>
          <Button className="mt-4 w-full" variant="outline" onClick={() => setMode("ask")}>
            Báo thêm vấn đề khác
          </Button>
        </section>
      )}

      {healthLog.length > 0 && (
        <section className="surface-card p-5">
          <h2 className="text-sm font-bold uppercase text-muted-foreground">Nhật ký sức khỏe</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {healthLog.map((h) => (
              <li key={h.id} className="flex gap-3">
                <span className="w-12 shrink-0 font-mono text-xs text-muted-foreground">
                  {h.at}
                </span>
                <span className="min-w-0">{h.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
