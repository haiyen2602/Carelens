"use client";

import { Lock, Plus, Search, Unlock, UserCog } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ACCOUNTS,
  type Account,
  type AccountRole,
  type AccountStatus,
  roleLabel,
  statusLabel,
} from "@/lib/admin-mock";

const roleTone: Record<AccountRole, string> = {
  doctor: "bg-success/15 text-success",
  patient: "bg-primary/10 text-primary",
  caregiver: "bg-warning/25 text-warning-foreground",
  admin: "bg-accent text-accent-foreground",
};

const statusTone: Record<AccountStatus, string> = {
  active: "bg-success/15 text-success",
  locked: "bg-destructive/12 text-destructive",
  pending: "bg-warning/25 text-warning-foreground",
};

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>(ACCOUNTS);
  const [q, setQ] = useState("");
  const [role, setRole] = useState<"all" | AccountRole>("all");
  const [status, setStatus] = useState<"all" | AccountStatus>("all");

  const list = useMemo(
    () =>
      accounts.filter((a) => {
        const matchQ =
          a.name.toLowerCase().includes(q.toLowerCase()) ||
          a.id.toLowerCase().includes(q.toLowerCase()) ||
          a.phone.includes(q);
        const matchRole = role === "all" || a.role === role;
        const matchStatus = status === "all" || a.status === status;
        return matchQ && matchRole && matchStatus;
      }),
    [accounts, q, role, status],
  );

  const toggleLock = (id: string) =>
    setAccounts((prev) =>
      prev.map((a) =>
        a.id === id ? { ...a, status: a.status === "locked" ? "active" : "locked" } : a,
      ),
    );

  const activate = (id: string) =>
    setAccounts((prev) => prev.map((a) => (a.id === id ? { ...a, status: "active" } : a)));

  return (
    <div className="space-y-6">
      <header className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-extrabold tracking-tight">Quản lý tài khoản</h1>
          <p className="text-sm text-muted-foreground">
            {accounts.length} tài khoản · bác sĩ, bệnh nhân, người thân và quản trị viên.
          </p>
        </div>
        <Button>
          <Plus className="mr-1 h-4 w-4" /> Tạo tài khoản
        </Button>
      </header>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm theo tên, ID, số điện thoại..."
            className="pl-9"
          />
        </div>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as "all" | AccountRole)}
          className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
        >
          <option value="all">Vai trò: Tất cả</option>
          <option value="doctor">Bác sĩ</option>
          <option value="patient">Bệnh nhân</option>
          <option value="caregiver">Người thân</option>
          <option value="admin">Quản trị</option>
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as "all" | AccountStatus)}
          className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
        >
          <option value="all">Trạng thái: Tất cả</option>
          <option value="active">Hoạt động</option>
          <option value="locked">Đã khoá</option>
          <option value="pending">Chờ kích hoạt</option>
        </select>
      </div>

      <div className="surface-card overflow-x-auto">
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/60 text-left text-xs font-semibold text-muted-foreground">
              <th className="px-4 py-3">Tài khoản</th>
              <th className="px-4 py-3">Vai trò</th>
              <th className="px-4 py-3">Liên hệ</th>
              <th className="px-4 py-3">Trạng thái</th>
              <th className="px-4 py-3">Đăng nhập cuối</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {list.map((a) => (
              <tr key={a.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-xs font-bold text-accent-foreground">
                      {a.name.charAt(0)}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{a.name}</p>
                      <p className="text-xs text-muted-foreground">{a.id}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-md px-2 py-1 text-xs font-semibold ${roleTone[a.role]}`}
                  >
                    {roleLabel[a.role]}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <p>{a.phone}</p>
                  <p className="text-xs text-muted-foreground">{a.email}</p>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-md px-2 py-1 text-xs font-semibold ${statusTone[a.status]}`}
                  >
                    {statusLabel[a.status]}
                  </span>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{a.lastLogin}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    {a.status === "pending" ? (
                      <Button variant="outline" size="sm" onClick={() => activate(a.id)}>
                        <UserCog className="mr-1 h-3.5 w-3.5" /> Kích hoạt
                      </Button>
                    ) : (
                      <Button variant="outline" size="sm" onClick={() => toggleLock(a.id)}>
                        {a.status === "locked" ? (
                          <>
                            <Unlock className="mr-1 h-3.5 w-3.5" /> Mở khoá
                          </>
                        ) : (
                          <>
                            <Lock className="mr-1 h-3.5 w-3.5" /> Khoá
                          </>
                        )}
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {list.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  Không tìm thấy tài khoản phù hợp.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
