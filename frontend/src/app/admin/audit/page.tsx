"use client";

import { AlertCircle, ChevronLeft, ChevronRight, Loader2, Lock, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { listSystemAuditLogs, type SystemAuditLogEntry } from "@/lib/audit";

const roleTone: Record<string, string> = {
  doctor: "bg-success/15 text-success",
  patient: "bg-primary/10 text-primary",
  caregiver: "bg-warning/25 text-warning-foreground",
  admin: "bg-accent text-accent-foreground",
  "Hệ thống": "bg-muted text-muted-foreground",
  system: "bg-muted text-muted-foreground",
};

const roleDisplayName: Record<string, string> = {
  admin: "Quản trị",
  doctor: "Bác sĩ",
  patient: "Bệnh nhân",
  caregiver: "Người thân",
  system: "Hệ thống",
  "Hệ thống": "Hệ thống",
};

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isCleanTarget(target?: string | null): boolean {
  if (!target) return false;
  return !UUID_REGEX.test(target.trim());
}


function formatDateTime(isoString: string) {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return { date: isoString, time: "" };
    const date = d.toLocaleDateString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
    const time = d.toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
    });
    return { date, time };
  } catch {
    return { date: isoString, time: "" };
  }
}

export default function AdminAuditPage() {
  const { accessToken } = useAuth();
  const [q, setQ] = useState("");
  const [role, setRole] = useState("all");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<SystemAuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const debounce = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      listSystemAuditLogs({
        q,
        role: role === "all" ? undefined : role,
        page,
        pageSize: 20,
        accessToken,
        signal: controller.signal,
      })
        .then((result) => {
          setItems(result.items);
          setTotal(result.total);
          setTotalPages(result.total_pages);
        })
        .catch((reason: unknown) => {
          if (!controller.signal.aborted) {
            setError(reason instanceof Error ? reason.message : "Không thể tải log hệ thống");
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 300);

    return () => {
      window.clearTimeout(debounce);
      controller.abort();
    };
  }, [accessToken, page, q, role]);

  const changeQuery = (val: string) => {
    setQ(val);
    setPage(1);
  };

  const changeRole = (val: string) => {
    setRole(val);
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-xl border border-warning/40 bg-warning/10 p-4">
        <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warning-foreground" />
        <p className="text-sm text-warning-foreground">
          Audit log chỉ đọc (read-only), kể cả với quản trị viên — đây là ràng buộc an toàn của sản phẩm.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search
            aria-hidden="true"
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={q}
            onChange={(e) => changeQuery(e.target.value)}
            placeholder="Tìm theo người thực hiện, hành động, đối tượng..."
            aria-label="Tìm theo người thực hiện hoặc hành động"
            className="pl-9"
          />
        </div>
        <select
          value={role}
          onChange={(e) => changeRole(e.target.value)}
          aria-label="Lọc theo vai trò"
          className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
        >
          <option value="all">Vai trò: Tất cả</option>
          <option value="admin">Quản trị</option>
          <option value="doctor">Bác sĩ</option>
          <option value="patient">Bệnh nhân</option>
          <option value="caregiver">Người thân</option>
          <option value="Hệ thống">Hệ thống / Agent</option>
        </select>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      <div className="surface-card divide-y divide-border">
        {loading ? (
          <div className="p-8 text-center text-muted-foreground">
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
            <p className="mt-2 text-sm">Đang tải nhật ký kiểm toán...</p>
          </div>
        ) : items.length === 0 ? (
          <p className="p-8 text-center text-muted-foreground">Không tìm thấy bản ghi phù hợp.</p>
        ) : (
          items.map((a) => {
            const { date, time } = formatDateTime(a.created_at);
            return (
              <div key={a.id} className="flex flex-wrap items-start gap-4 p-4">
                <div className="w-24 shrink-0">
                  <p className="text-sm font-semibold">{date}</p>
                  {time && <p className="font-mono text-xs text-muted-foreground">{time}</p>}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{a.actor_name}</p>
                  <p className="text-sm text-muted-foreground">{a.action}</p>
                  {isCleanTarget(a.target) && (
                    <p className="mt-1 text-xs text-muted-foreground">Đối tượng: {a.target}</p>
                  )}
                </div>
                <span
                  className={`shrink-0 rounded-md px-2 py-1 text-xs font-semibold ${
                    roleTone[a.actor_role] ?? "bg-muted text-muted-foreground"
                  }`}
                >
                  {roleDisplayName[a.actor_role] ?? a.actor_role}
                </span>
              </div>
            );
          })
        )}
      </div>

      {totalPages > 1 && (
        <nav aria-label="Phân trang" className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">Tổng cộng {total} bản ghi</p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              aria-label="Trang trước"
              disabled={page <= 1 || loading}
              onClick={() => setPage((current) => current - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm text-muted-foreground">
              Trang {page}/{totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              aria-label="Trang sau"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((current) => current + 1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </nav>
      )}
    </div>
  );
}
