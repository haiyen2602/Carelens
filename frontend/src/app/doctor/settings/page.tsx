"use client";

import { useState } from "react";
import { Switch } from "@/components/ui/switch";

const options = [
  ["Nhận cảnh báo nghiêm trọng qua SMS", true],
  ["Tự động đẩy cảnh báo bỏ liều sau 3 lần nhắc", true],
  ["Cho phép AI đề xuất đổi giờ uống", true],
  ["Nhận báo cáo tuân thủ hằng tuần qua email", false],
] as const;

export default function SettingsPage() {
  const [state, setState] = useState<boolean[]>(options.map((o) => o[1]));
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Cài đặt</h1>
        <p className="text-sm text-muted-foreground">Khung an toàn liều mặc định: ±30 phút.</p>
      </header>
      <div className="surface-card divide-y divide-border">
        {options.map(([label], i) => (
          <div key={label} className="flex items-center justify-between gap-4 p-5">
            <p className="min-w-0 text-sm font-medium">{label}</p>
            <Switch
              checked={state[i] ?? false}
              onCheckedChange={(v) => setState((s) => s.map((x, j) => (j === i ? v : x)))}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
