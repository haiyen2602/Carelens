"use client";

const fields = [
  ["Họ và tên", "BS. Phạm Quốc Huy"],
  ["Mã bác sĩ", "BS-0114"],
  ["Chuyên khoa", "Nội tổng quát"],
  ["Cơ sở", "Bệnh viện Đa khoa Trung tâm"],
  ["Điện thoại", "0901 234 567"],
  ["Email", "huy.pham@capymedi.vn"],
];

export default function ProfilePage() {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Hồ sơ cá nhân</h1>
        <p className="text-sm text-muted-foreground">
          Thông tin hiển thị với bệnh nhân và người thân.
        </p>
      </header>
      <div className="surface-card p-6">
        <div className="flex items-center gap-4">
          <span className="grid h-16 w-16 place-items-center rounded-full bg-accent text-xl font-bold text-accent-foreground">
            H
          </span>
          <div>
            <p className="text-lg font-bold">BS. Phạm Quốc Huy</p>
            <p className="text-sm text-muted-foreground">Nội tổng quát · BS-0114</p>
          </div>
        </div>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2">
          {fields.map(([k, v]) => (
            <div key={k} className="rounded-xl bg-muted p-4">
              <dt className="text-xs font-semibold uppercase text-muted-foreground">{k}</dt>
              <dd className="mt-1 font-semibold">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
