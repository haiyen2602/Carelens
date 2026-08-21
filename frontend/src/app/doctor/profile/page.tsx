"use client";

import { useAuth } from "@/lib/auth";

export default function ProfilePage() {
  const { user } = useAuth();
  // CHI hien thi field co nguon that tu backend (MeResponse: full_name,
  // email, doctor_id). Chuyen khoa/co so/dien thoai CHUA co cot tuong ung
  // o backend - khong bia so lieu, doi den khi co API that.
  const fields = [
    ["Họ và tên", user?.full_name ?? "—"],
    ["Mã bác sĩ (ID hệ thống)", user?.doctor_id ?? "—"],
    ["Email", user?.email ?? "—"],
  ];

  return (
    <div className="space-y-5">
      <div className="surface-card p-6">
        <div className="flex items-center gap-4">
          <span className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-accent text-xl font-bold text-accent-foreground">
            {(user?.full_name ?? "?").charAt(0)}
          </span>
          <div className="min-w-0">
            <p className="truncate text-lg font-bold">{user?.full_name ?? "Đang tải…"}</p>
            <p className="text-sm text-muted-foreground">Bác sĩ</p>
          </div>
        </div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2">
          {fields.map(([k, v]) => (
            <div key={k} className="rounded-xl bg-muted p-4">
              <dt className="text-xs font-semibold uppercase text-muted-foreground">{k}</dt>
              <dd className="mt-1 truncate font-semibold" title={v}>
                {v}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-xs text-muted-foreground">
          Chuyên khoa, cơ sở và số điện thoại chưa có trong hệ thống — sẽ hiển thị khi backend bổ
          sung các trường này.
        </p>
      </div>
    </div>
  );
}
