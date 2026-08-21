"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Plus, Search, Unlock } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { roleLabel, statusLabel } from "@/lib/admin-mock";
import { useAuth } from "@/lib/auth";
import {
  createAccount,
  listAccounts,
  updateAccountStatus,
  type AccountRecord,
  type AccountCreationRole,
  type AccountRole,
  type AccountStatus,
} from "@/lib/accounts";

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

const emptyForm = {
  email: "",
  password: "",
  fullName: "",
  role: "doctor" as AccountCreationRole,
};

type AccountGroup = "patients" | "doctors" | "admins";

function AccountsContent() {
  const queryClient = useQueryClient();
  const { accessToken } = useAuth();
  const searchParams = useSearchParams();
  const groupParam = searchParams.get("group");
  const initialGroup: AccountGroup =
    groupParam === "doctors" || groupParam === "admins" || groupParam === "patients"
      ? groupParam
      : "patients";

  const [q, setQ] = useState("");
  const [activeGroup, setActiveGroup] = useState<AccountGroup>(initialGroup);

  useEffect(() => {
    if (groupParam === "doctors" || groupParam === "admins" || groupParam === "patients") {
      setActiveGroup(groupParam);
    }
  }, [groupParam]);
  const [status, setStatus] = useState<"all" | AccountStatus>("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState("");
  const [statusError, setStatusError] = useState("");
  const [lastStatusAction, setLastStatusAction] = useState<{
    id: string;
    next: AccountStatus;
  } | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["accounts"],
    queryFn: () => listAccounts(accessToken),
    enabled: Boolean(accessToken),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createAccount({
        email: form.email,
        password: form.password,
        fullName: form.fullName,
        role: form.role,
        accessToken,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      setDialogOpen(false);
      setForm(emptyForm);
      setFormError("");
    },
    onError: (err: unknown) => {
      setFormError(err instanceof Error ? err.message : "Tạo tài khoản thất bại.");
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, next }: { id: string; next: AccountStatus }) =>
      updateAccountStatus(id, next, accessToken),
    onSuccess: () => {
      setStatusError("");
      setLastStatusAction(null);
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (err: unknown) => {
      setStatusError(err instanceof Error ? err.message : "Cập nhật trạng thái thất bại.");
    },
  });

  const accounts = accountsQuery.data ?? [];

  const groupAccounts = useMemo(
    () =>
      accounts.filter((a) => {
        const matchesGroup =
          activeGroup === "patients"
            ? a.role === "patient" || a.role === "caregiver"
            : activeGroup === "doctors"
              ? a.role === "doctor"
              : a.role === "admin";
        return matchesGroup;
      }),
    [accounts, activeGroup],
  );

  const list = useMemo(
    () =>
      groupAccounts.filter((a) => {
        const matchQ =
          a.fullName.toLowerCase().includes(q.toLowerCase()) ||
          a.email.toLowerCase().includes(q.toLowerCase());
        const matchStatus = status === "all" || a.status === status;
        return matchQ && matchStatus;
      }),
    [groupAccounts, q, status],
  );

  const submitCreate = (e: FormEvent) => {
    e.preventDefault();
    if (!form.email.trim() || !form.password.trim() || !form.fullName.trim()) {
      setFormError("Vui lòng nhập đầy đủ email, mật khẩu và họ tên.");
      return;
    }
    if (form.password.length < 8) {
      setFormError("Mật khẩu tối thiểu 8 ký tự.");
      return;
    }
    setFormError("");
    createMutation.mutate();
  };

  const groupNames: Record<AccountGroup, string> = {
    patients: "Bệnh nhân",
    doctors: "Bác sĩ",
    admins: "Admin",
  };

  return (
    <div className="space-y-6">
      <header className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-extrabold tracking-tight">
            Tài khoản: {groupNames[activeGroup]}
          </h1>
          <p className="text-sm text-muted-foreground">
            {groupAccounts.length} tài khoản trong nhóm {groupNames[activeGroup].toLowerCase()}.
          </p>
        </div>
        {activeGroup !== "patients" && (
          <Dialog
            open={dialogOpen}
            onOpenChange={(open) => {
              setDialogOpen(open);
              if (!open) {
                setForm(emptyForm);
                setFormError("");
              }
            }}
          >
            <DialogTrigger asChild>
              <Button>
                <Plus className="mr-1 h-4 w-4" /> Tạo tài khoản
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Tạo tài khoản mới</DialogTitle>
                <DialogDescription>
                  Không có đăng ký công khai — chỉ quản trị viên tạo được tài khoản.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={submitCreate} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="full_name">Họ tên</Label>
                  <Input
                    id="full_name"
                    value={form.fullName}
                    onChange={(e) => setForm((f) => ({ ...f, fullName: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Mật khẩu</Label>
                  <Input
                    id="password"
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Vai trò</Label>
                  <Select
                    value={form.role}
                    onValueChange={(v) =>
                      setForm((f) => ({ ...f, role: v as AccountCreationRole }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(["doctor", "admin"] as const).map((r) => (
                        <SelectItem key={r} value={r}>
                          {roleLabel[r]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {formError && <p className="text-sm font-medium text-destructive">{formError}</p>}
                <DialogFooter>
                  <Button type="submit" disabled={createMutation.isPending}>
                    {createMutation.isPending ? "Đang tạo..." : "Tạo tài khoản"}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </header>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search
            aria-hidden="true"
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm theo tên hoặc email..."
            aria-label="Tìm theo tên hoặc email"
            className="pl-9"
          />
        </div>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as "all" | AccountStatus)}
          aria-label="Lọc theo trạng thái"
          className="h-10 rounded-xl border border-input bg-card px-3 text-sm text-muted-foreground outline-none"
        >
          <option value="all">Trạng thái: Tất cả</option>
          <option value="active">Hoạt động</option>
          <option value="locked">Đã khoá</option>
        </select>
      </div>

      {statusError && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          <span>{statusError}</span>
          <div className="flex items-center gap-2">
            {lastStatusAction && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={statusMutation.isPending}
                onClick={() => {
                  setStatusError("");
                  statusMutation.mutate(lastStatusAction);
                }}
              >
                Thử lại
              </Button>
            )}
            <Button type="button" variant="ghost" size="sm" onClick={() => setStatusError("")}>
              Đóng
            </Button>
          </div>
        </div>
      )}

      <div className="surface-card overflow-x-auto">
        <table className="w-full min-w-[800px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/60 text-left text-xs font-semibold text-muted-foreground">
              <th className="px-4 py-3">Tài khoản</th>
              <th className="px-4 py-3">Vai trò</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Liên kết</th>
              <th className="px-4 py-3">Trạng thái</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {accountsQuery.isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  Đang tải...
                </td>
              </tr>
            )}
            {accountsQuery.isError && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-destructive">
                  Không tải được danh sách tài khoản.
                </td>
              </tr>
            )}
            {list.map((a: AccountRecord) => (
              <tr key={a.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-xs font-bold text-accent-foreground">
                      {a.fullName.charAt(0).toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-semibold" title={a.fullName}>
                        {a.fullName}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">{a.id}</p>
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
                <td className="px-4 py-3 text-muted-foreground">{a.email}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {a.patientId && <p>patient: {a.patientId}</p>}
                  {a.doctorId && <p>doctor: {a.doctorId}</p>}
                  {!a.patientId && !a.doctorId && "—"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-md px-2 py-1 text-xs font-semibold ${statusTone[a.status]}`}
                  >
                    {statusLabel[a.status]}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={statusMutation.isPending}
                      onClick={() => {
                        setStatusError("");
                        const action: { id: string; next: AccountStatus } = {
                          id: a.id,
                          next: a.status === "locked" ? "active" : "locked",
                        };
                        setLastStatusAction(action);
                        statusMutation.mutate(action);
                      }}
                    >
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
                  </div>
                </td>
              </tr>
            ))}
            {!accountsQuery.isLoading && !accountsQuery.isError && list.length === 0 && (
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

export default function AccountsPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-6">
          <div className="h-8 w-48 animate-pulse rounded-md bg-muted" />
          <div className="h-64 w-full animate-pulse rounded-xl bg-muted/40" />
        </div>
      }
    >
      <AccountsContent />
    </Suspense>
  );
}
