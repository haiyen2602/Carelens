"use client";

import { Eye, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useProto } from "@/lib/proto-store";
import { listDoses, type Dose } from "@/lib/doses";

function gioHienThi(iso: string): string {
  return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function moTaThuoc(d: Dose): string {
  return d.expectedItems.map((it) => it.tenThuoc).join(", ") || "(chưa rõ tên thuốc)";
}

export default function PatientsPage() {
  const { patients, toggleWatch } = useProto();
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  // Lich uong hom nay CUA DUNG benh nhan dang mo ho so - GET /doses can
  // patient_id (khong co endpoint liet ke gop nhieu benh nhan cung luc), nen
  // tai rieng moi khi mo mot ho so thay vi dung mot mang `doses` toan cuc.
  const [dosesCuaHoSo, setDosesCuaHoSo] = useState<Dose[]>([]);
  const [dangTai, setDangTai] = useState(false);
  const withDisplayId = patients.map((p, i) => ({
    ...p,
    displayId: `BN${String(i + 1).padStart(4, "0")}`,
  }));
  const query = q.trim().toLowerCase();
  const list = withDisplayId.filter(
    (p) => p.name.toLowerCase().includes(query) || p.displayId.toLowerCase().includes(query),
  );

  useEffect(() => {
    if (!openId) {
      setDosesCuaHoSo([]);
      return;
    }
    let cancelled = false;
    setDangTai(true);
    listDoses(openId)
      .then((ds) => {
        if (!cancelled) setDosesCuaHoSo(ds);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setDangTai(false);
      });
    return () => {
      cancelled = true;
    };
  }, [openId]);

  return (
    <div className="space-y-6">
      <header className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-extrabold tracking-tight">Danh sách bệnh nhân</h1>
          <p className="text-sm text-muted-foreground">
            Filter theo tên, mở hồ sơ để xem chi tiết.
          </p>
        </div>
        <Input
          placeholder="Tìm theo tên hoặc ID bệnh nhân…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full sm:w-64"
        />
      </header>

      <div className="space-y-3">
        {list.map((p) => (
          <div key={p.id} className="surface-card p-5">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent font-bold text-accent-foreground">
                  {p.name.charAt(0)}
                </span>
                <div className="min-w-0">
                  <p className="flex items-center gap-2 truncate font-semibold">
                    {p.name}
                    {p.watch && (
                      <span className="inline-flex shrink-0 items-center gap-1 rounded bg-warning/25 px-1.5 py-0.5 text-[11px] font-semibold text-warning-foreground">
                        <ShieldAlert className="h-3 w-3" /> Theo dõi
                      </span>
                    )}
                  </p>
                  <p className="truncate text-sm text-muted-foreground">
                    ID: {p.displayId} · {p.age} tuổi · {p.condition}
                  </p>
                </div>
              </div>
              <div className="grid shrink-0 grid-cols-[9rem_6.5rem_7rem] items-center gap-4">
                <div className="hidden sm:block">
                  <p className="whitespace-nowrap text-xs text-muted-foreground">
                    Tuân thủ {p.adherence}%
                  </p>
                  <Progress value={p.adherence} className="mt-1 h-2" />
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="justify-self-start"
                  onClick={() => setOpenId(openId === p.id ? null : p.id)}
                >
                  <Eye className="mr-1 h-4 w-4" /> Hồ sơ
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="justify-self-start whitespace-nowrap"
                  onClick={() => toggleWatch(p.id)}
                >
                  {p.watch ? "Bỏ theo dõi" : "Theo dõi"}
                </Button>
              </div>
            </div>

            {openId === p.id && (
              <div className="mt-5 space-y-3 rounded-lg bg-muted p-4">
                <p className="text-sm font-semibold">Lịch sử liều hôm nay</p>
                {dangTai && <p className="text-sm text-muted-foreground">Đang tải…</p>}
                {!dangTai && dosesCuaHoSo.length === 0 && (
                  <p className="text-sm text-muted-foreground">Chưa có lịch uống thuốc nào.</p>
                )}
                <ul className="space-y-2 text-sm">
                  {dosesCuaHoSo.map((d) => (
                    <li key={d.id} className="flex items-center justify-between gap-3">
                      <span className="min-w-0 truncate">
                        {gioHienThi(d.scheduledAt)} · {moTaThuoc(d)}
                      </span>
                      <span className="shrink-0 text-xs font-semibold text-muted-foreground">
                        {d.status}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
