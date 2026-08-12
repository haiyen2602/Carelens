"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Plus, Search, Unlock } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
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
import {
  createAccount,
  listAccounts,
  roleLabel,
  statusLabel,
  updateAccountStatus,
  type Account,
  type AccountRole,
  type AccountStatus,
} from "@/lib/accounts";
import { useAuth } from "@/lib/auth";

const roleTone: Record<AccountRole, string> = {
  doctor: "bg-success/15 text-success",
  patient: "bg-primary/10 text-primary",
  caregiver: "bg-warning/25 text-warning-foreground",
  admin: "bg-accent text-accent-foreground",
};

const statusTone: Record<AccountStatus, string> = {
  active: "bg-success/15 text-success",
  locked: "bg-destructive/12 text-destructive",
};

const emptyForm = {
  email: "",
  password: "",
  full_name: "",
  role: "patient" as AccountRole,
  patient_id: "",
  doctor_id: "",
};

export default function AccountsPage() {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [role, setRole] = useState<"all" | AccountRole>("all");
  const [status, setStatus] = useState<"all" | AccountStatus>("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState("");

  const accountsQuery = useQuery({
    queryKey: ["accounts"],
    queryFn: () => listAccounts(accessToken!),
    enabled: !!accessToken,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createAccount(accessToken!, {
        email: form.email,
        password: form.password,
        full_name: form.full_name,
        role: form.role,
        patient_id: form.role === "patient" ? form.patient_id || null : null,
        doctor_id: form.role === "patient" ? form.doctor_id || null : null,
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
      updateAccountStatus(accessToken!, id, next),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["accounts"] }),
  });

  const accounts = accountsQuery.data ?? [];

  const list = useMemo(
    () =>
      accounts.filter((a) => {
        const matchQ =
          a.full_name.toLowerCase().includes(q.toLowerCase()) ||
          a.email.toLowerCase().includes(q.toLowerCase());
        const matchRole = role === "all" || a.role === role;
        const matchStatus = status === "all" || a.status === status;
        return matchQ && matchRole && matchStatus;
      }),
    [accounts, q, role, status],
  );

  const submitCreate = (e: FormEvent) => {
    e.preventDefault();
    if (!form.email.trim() || !form.password.trim() || !form.full_name.trim()) {
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

  return (
    <div className="space-y-6">
      <header className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-extrabold tracking-tight">Quản lý tài khoản</h1>
          <p className="text-sm text-muted-foreground">
            {accounts.length} tài khoản · bác sĩ, bệnh nhân, người thân và quản trị viên.
          </p>
        </div>
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
                  value={form.full_name}
                  onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
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
                  onValueChange={(v) => setForm((f) => ({ ...f, role: v as AccountRole }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(roleLabel) as AccountRole[]).map((r) => (
                      <SelectItem key={r} value={r}>
                        {roleLabel[r]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {form.role === "patient" && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="patient_id">
                      Patient ID{" "}
                      <span className="text-muted-foreground">
                        (tuỳ chọn, để khớp dữ liệu demo có sẵn)
                      </span>
                    </Label>
                    <Input
                      id="patient_id"
                      placeholder="vd demo-patient-01"
                      value={form.patient_id}
                      onChange={(e) => setForm((f) => ({ ...f, patient_id: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="doctor_id">
                      Doctor ID{" "}
                      <span className="text-muted-foreground">(tuỳ chọn — bác sĩ phụ trách)</span>
                    </Label>
                    <Input
                      id="doctor_id"
                      value={form.doctor_id}
                      onChange={(e) => setForm((f) => ({ ...f, doctor_id: e.target.value }))}
                    />
                  </div>
                </>
              )}
              {formError && <p className="text-sm font-medium text-destructive">{formError}</p>}
              <DialogFooter>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? "Đang tạo..." : "Tạo tài khoản"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </header>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Tìm theo tên hoặc email..."
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
        </select>
      </div>

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
            {list.map((a: Account) => (
              <tr key={a.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-xs font-bold text-accent-foreground">
                      {a.full_name.charAt(0).toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{a.full_name}</p>
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
                  {a.patient_id && <p>patient: {a.patient_id}</p>}
                  {a.doctor_id && <p>doctor: {a.doctor_id}</p>}
                  {!a.patient_id && !a.doctor_id && "—"}
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
                      onClick={() =>
                        statusMutation.mutate({
                          id: a.id,
                          next: a.status === "locked" ? "active" : "locked",
                        })
                      }
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
            {!accountsQuery.isLoading && list.length === 0 && (
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
