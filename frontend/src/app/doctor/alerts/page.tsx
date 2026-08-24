"use client";

import {
  AlertTriangle,
  ChevronRight,
  Clock,
  Mail,
  Phone,
  Search,
  UserRound,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { HoverSelect } from "@/components/hover-select";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { presentAlert } from "@/lib/alert-presentation";
import { boDau } from "@/lib/text";
import { useProto, type AlertLevel, type SysAlert } from "@/lib/proto-store";

const tone: Record<AlertLevel, string> = {
  low: "bg-secondary text-secondary-foreground",
  mid: "bg-warning/25 text-warning-foreground",
  high: "bg-destructive/15 text-destructive",
};

const levelLabel: Record<AlertLevel, string> = {
  low: "Nhẹ",
  mid: "Trung bình",
  high: "Nghiêm trọng",
};

const barTone: Record<AlertLevel, string> = {
  low: "bg-primary",
  mid: "bg-warning",
  high: "bg-destructive",
};

// Mau rieng cho trang thai xu ly - truoc day o day chi la chu xam, khong phan
// biet duoc "Mới" voi "Đã xử lý" khi luot nhanh danh sach.
//
// Luu y `text-success` chu KHONG phai `text-success-foreground`: bien
// --success-foreground gan nhu trang (danh cho chu TREN nen success dac), dat
// len nen success/15 nhat se mat chu. --warning-foreground thi nguoc lai (mau
// toi) nen dung duoc truc tiep - hai bien khong cung quy uoc, xem globals.css.
const statusTone: Record<SysAlert["status"], string> = {
  new: "bg-primary/10 text-primary",
  processing: "bg-warning/25 text-warning-foreground",
  acknowledged: "bg-secondary text-secondary-foreground",
  resolved: "bg-success/15 text-success",
  dismissed: "bg-muted text-muted-foreground",
};

const LEVEL_OPTIONS = [
  { value: "all", label: "Mọi mức độ" },
  { value: "high", label: "Nghiêm trọng" },
  { value: "mid", label: "Trung bình" },
  { value: "low", label: "Nhẹ" },
];

// "Đang xử lý" (processing) KHONG co trong danh sach nay: khong con duong nao
// tao ra trang thai do tu du lieu that (xem SysAlert trong proto-store) nen
// mot muc loc luon tra ve 0 ket qua chi lam nguoi dung tuong he thong hong.
const STATUS_OPTIONS = [
  { value: "all", label: "Mọi trạng thái" },
  { value: "new", label: "Mới" },
  { value: "acknowledged", label: "Đã ghi nhận" },
  { value: "resolved", label: "Đã xử lý" },
  { value: "dismissed", label: "Đã từ chối" },
];

type DateRange = "all" | "today" | "7d" | "30d" | "custom";

const DATE_OPTIONS: { value: DateRange; label: string }[] = [
  { value: "all", label: "Mọi thời điểm" },
  { value: "today", label: "Hôm nay" },
  { value: "7d", label: "7 ngày qua" },
  { value: "30d", label: "30 ngày qua" },
  { value: "custom", label: "Khoảng tuỳ chọn…" },
];

// Ba hanh dong o cuoi popup. `verb` dung cho cau thong bao sau khi luu ("Đã
// ghi nhận cảnh báo"), tach khoi `label` tren nut vi hai cho doc khac nhau.
const ACTIONS: {
  status: Extract<SysAlert["status"], "acknowledged" | "resolved" | "dismissed">;
  label: string;
  verb: string;
  variant: "default" | "outline" | "ghost";
  className?: string;
}[] = [
  {
    status: "dismissed",
    label: "Từ chối",
    verb: "Đã từ chối cảnh báo",
    variant: "ghost",
    className: "text-destructive",
  },
  { status: "acknowledged", label: "Ghi nhận", verb: "Đã ghi nhận cảnh báo", variant: "outline" },
  { status: "resolved", label: "Đánh dấu đã xử lý", verb: "Đã đánh dấu xử lý", variant: "default" },
];

// Thoi gian giu nut "Hoàn tác" trong toast. Dai hon mac dinh cua sonner (4s)
// vi day la thao tac ghi xuong DB - bam nham can du thi gian nhan ra.
const UNDO_MS = 8000;

function dauNgay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

/** Bien lua chon khoang ngay thanh cap moc [tu, den) theo gio DIA PHUONG cua
 * may bac si - `createdAt` la ISO UTC nen so sanh truc tiep chuoi se lech mui
 * gio (canh bao 20:30 gio VN nam o ngay hom truoc theo UTC). */
function khoangNgay(
  range: DateRange,
  tuNgay: string,
  denNgay: string,
): { tu: Date | null; den: Date | null } {
  const homNay = dauNgay(new Date());
  if (range === "today") {
    return { tu: homNay, den: new Date(homNay.getTime() + 86400000) };
  }
  if (range === "7d" || range === "30d") {
    const soNgay = range === "7d" ? 7 : 30;
    const tu = new Date(homNay);
    tu.setDate(tu.getDate() - (soNgay - 1));
    return { tu, den: new Date(homNay.getTime() + 86400000) };
  }
  if (range === "custom") {
    // Moi o co the de trong - loc mot dau (vd "từ 01/08 tro di") van hop le.
    const tu = tuNgay ? dauNgay(new Date(`${tuNgay}T00:00:00`)) : null;
    const den = denNgay ? new Date(`${denNgay}T00:00:00`) : null;
    if (den) den.setDate(den.getDate() + 1); // bao gom tron ngay "đến"
    return { tu, den };
  }
  return { tu: null, den: null };
}

function ngayGioHienThi(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AlertsPage() {
  const { alerts, patients, familyContacts, setAlertStatus } = useProto();
  const [openId, setOpenId] = useState<string | null>(null);
  const watchedCount = patients.filter((p) => p.watch).length;

  // Bo loc song trong state CUA TRANG, khong dat vao proto-store: chuong thong
  // bao o doctor/layout.tsx va bo dem o doctor/page.tsx doc chung mang
  // `alerts`, loc trong store se lam sai ca hai cho do.
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("all");
  const [status, setStatus] = useState("all");
  const [range, setRange] = useState<DateRange>("all");
  const [tuNgay, setTuNgay] = useState("");
  const [denNgay, setDenNgay] = useState("");

  // Xac nhan 2 buoc cho 3 nut trang thai - `pending` la hanh dong dang cho
  // xac nhan, null nghia la dang hien hang nut binh thuong.
  const [pending, setPending] = useState<(typeof ACTIONS)[number] | null>(null);
  const [saving, setSaving] = useState(false);

  const tenBenhNhan = useMemo(
    () => new Map(patients.map((p) => [p.id, p.name])),
    [patients],
  );

  const hienThi = useMemo(() => {
    const tuKhoa = boDau(q.trim());
    const { tu, den } = khoangNgay(range, tuNgay, denNgay);

    return alerts.filter((a) => {
      if (level !== "all" && a.level !== level) return false;
      if (status !== "all" && a.status !== status) return false;

      if (tu || den) {
        const luc = new Date(a.createdAt).getTime();
        if (tu && luc < tu.getTime()) return false;
        if (den && luc >= den.getTime()) return false;
      }

      if (tuKhoa) {
        // Tim theo ten benh nhan HOAC ma benh nhan - bac si nho ten la chinh,
        // nhung ma BN la thu duy nhat khong trung nhau khi co hai nguoi
        // cung ten.
        const ten = tenBenhNhan.get(a.patientId) ?? "";
        if (!boDau(`${ten} ${a.patientId}`).includes(tuKhoa)) return false;
      }
      return true;
    });
  }, [alerts, level, status, range, tuNgay, denNgay, q, tenBenhNhan]);

  const coBoLoc =
    q.trim() !== "" || level !== "all" || status !== "all" || range !== "all";

  const xoaBoLoc = () => {
    setQ("");
    setLevel("all");
    setStatus("all");
    setRange("all");
    setTuNgay("");
    setDenNgay("");
  };

  const selected = alerts.find((a) => a.id === openId) ?? null;
  const selectedView = selected ? presentAlert(selected, patients) : null;
  const selectedPatient = selected ? patients.find((p) => p.id === selected.patientId) : undefined;
  const nguoiThan = selected
    ? familyContacts.filter((c) => c.patientId === selected.patientId)
    : [];

  // Moi lan mo canh bao khac (hoac dong popup) thi bo hanh dong dang cho xac
  // nhan - neu khong, mo canh bao B se thay thanh xac nhan con sot cua A.
  useEffect(() => {
    setPending(null);
  }, [openId]);

  const xacNhan = async () => {
    if (!selected || !pending) return;
    const id = selected.id;
    const truocDo = selected.status;
    const { status: moi, verb } = pending;

    setSaving(true);
    try {
      await setAlertStatus(id, moi);
      setOpenId(null);
      toast.success(verb, {
        duration: UNDO_MS,
        action: {
          label: "Hoàn tác",
          onClick: () => {
            setAlertStatus(id, truocDo).catch((err: unknown) => {
              toast.error(err instanceof Error ? err.message : "Không hoàn tác được.");
            });
          },
        },
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Không cập nhật được trạng thái cảnh báo.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="surface-card space-y-3 p-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_10rem_11rem_11rem]">
          <div className="relative">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm theo tên hoặc mã bệnh nhân…"
              aria-label="Tìm theo tên hoặc mã bệnh nhân"
              className="pl-9"
            />
          </div>
          <HoverSelect value={level} onChange={setLevel} options={LEVEL_OPTIONS} />
          <HoverSelect value={status} onChange={setStatus} options={STATUS_OPTIONS} />
          <HoverSelect
            value={range}
            onChange={(v) => setRange(v as DateRange)}
            options={DATE_OPTIONS}
          />
        </div>

        {range === "custom" && (
          <div className="grid gap-3 sm:grid-cols-2 lg:max-w-md">
            <label className="text-sm">
              <span className="text-muted-foreground">Từ ngày</span>
              <Input
                type="date"
                value={tuNgay}
                max={denNgay || undefined}
                onChange={(e) => setTuNgay(e.target.value)}
                className="mt-1"
              />
            </label>
            <label className="text-sm">
              <span className="text-muted-foreground">Đến ngày</span>
              <Input
                type="date"
                value={denNgay}
                min={tuNgay || undefined}
                onChange={(e) => setDenNgay(e.target.value)}
                className="mt-1"
              />
            </label>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
          <p>
            Hiển thị <span className="font-semibold text-foreground">{hienThi.length}</span> /{" "}
            {alerts.length} cảnh báo
          </p>
          {coBoLoc && (
            <Button variant="ghost" size="sm" onClick={xoaBoLoc}>
              <X className="mr-1 h-4 w-4" /> Xoá bộ lọc
            </Button>
          )}
        </div>
      </section>

      {alerts.length === 0 && watchedCount === 0 && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Bạn chưa theo dõi bệnh nhân nào nên chưa có cảnh báo nào tới bác sĩ — bấm{" "}
          <span className="font-semibold text-foreground">Theo dõi</span> ở trang{" "}
          <Link href="/doctor/patients" className="font-semibold text-primary">
            Quản lý bệnh nhân
          </Link>{" "}
          để nhận cảnh báo của họ tại đây.
        </div>
      )}
      {alerts.length === 0 && watchedCount > 0 && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Chưa có cảnh báo nào cho {watchedCount} bệnh nhân bạn đang theo dõi.
        </div>
      )}
      {alerts.length > 0 && hienThi.length === 0 && (
        <div className="surface-card p-10 text-center text-sm text-muted-foreground">
          Không có cảnh báo nào khớp bộ lọc hiện tại.
        </div>
      )}

      <div className="space-y-2">
        {hienThi.map((a) => {
          const alert = presentAlert(a, patients);
          const handled = a.status === "resolved" || a.status === "dismissed";

          return (
            <button
              key={a.id}
              onClick={() => setOpenId(a.id)}
              className={`surface-card flex w-full items-center gap-0 overflow-hidden p-0 text-left transition-colors hover:bg-muted/40 ${
                handled ? "opacity-60" : ""
              }`}
            >
              <span className={`w-1.5 shrink-0 self-stretch ${barTone[a.level]}`} />

              <span className="flex min-w-0 flex-1 items-center gap-3 p-4">
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${tone[a.level]}`}
                    >
                      {levelLabel[a.level]}
                    </span>
                    <span className="truncate font-bold">{alert.title}</span>
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <UserRound className="h-3.5 w-3.5" />
                      {alert.patientName}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5" />
                      {ngayGioHienThi(a.createdAt)}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusTone[a.status]}`}
                    >
                      {alert.statusLabel}
                    </span>
                  </span>
                </span>

                <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" />
              </span>
            </button>
          );
        })}
      </div>

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setOpenId(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          {selected && selectedView && (
            <>
              <DialogHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-bold ${tone[selected.level]}`}
                  >
                    {levelLabel[selected.level]}
                  </span>
                  <span
                    className={`rounded-full px-2 py-1 text-xs font-semibold ${statusTone[selected.status]}`}
                  >
                    {selectedView.statusLabel}
                  </span>
                  <span className="rounded bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground">
                    {selectedView.triggerLabel}
                  </span>
                </div>
                <DialogTitle className="pt-2 text-left text-lg">{selectedView.title}</DialogTitle>
              </DialogHeader>

              <div className="space-y-4">
                {/* Ho so benh nhan - hien THANG o day thay vi chi link sang
                    /doctor/patients: bac si dang xu ly canh bao khong nen phai
                    roi trang moi biet minh dang noi ve ai. */}
                <div className="rounded-lg border border-border p-3 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold">{selectedView.patientName}</p>
                      <p className="text-xs text-muted-foreground">Mã BN: {selected.patientId}</p>
                    </div>
                    <Button variant="outline" size="sm" asChild>
                      <Link href={`/doctor/patients?q=${encodeURIComponent(selected.patientId)}`}>
                        <UserRound className="mr-1 h-4 w-4" /> Hồ sơ đầy đủ
                      </Link>
                    </Button>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
                    {selectedPatient && (
                      <>
                        {selectedPatient.age > 0 && <span>{selectedPatient.age} tuổi</span>}
                        {selectedPatient.condition && <span>{selectedPatient.condition}</span>}
                        <span>
                          {selectedPatient.adherence === null
                            ? "Chưa có liều đến hạn"
                            : `Tuân thủ ${Math.round(selectedPatient.adherence)}%`}
                        </span>
                      </>
                    )}
                    <span className="inline-flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5" />
                      {ngayGioHienThi(selected.createdAt)}
                    </span>
                  </div>
                  {selectedPatient?.phone ? (
                    <a
                      href={`tel:${selectedPatient.phone}`}
                      className="mt-2 inline-flex items-center gap-1.5 font-semibold text-primary"
                    >
                      <Phone className="h-3.5 w-3.5" />
                      {selectedPatient.phone}
                    </a>
                  ) : (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Bệnh nhân chưa cập nhật số điện thoại.
                    </p>
                  )}
                </div>

                {/* Nguoi than - `email` la cach lien lac DUY NHAT he thong luu
                    (khong bang nao co so dien thoai cua nguoi than), xem
                    FamilyContact trong lib/proto-store.tsx. */}
                <div className="rounded-lg border border-border p-3 text-sm">
                  <p className="flex items-center gap-1.5 text-xs font-bold uppercase text-muted-foreground">
                    <Users className="h-3.5 w-3.5" /> Người thân liên hệ
                  </p>
                  {nguoiThan.length === 0 ? (
                    <p className="mt-2 text-muted-foreground">
                      Bệnh nhân này chưa có người thân nào được liên kết.
                    </p>
                  ) : (
                    <ul className="mt-2 space-y-2">
                      {nguoiThan.map((c) => (
                        <li
                          key={c.id}
                          className="flex flex-wrap items-center justify-between gap-2"
                        >
                          <span className="min-w-0">
                            <span className="font-semibold">{c.name}</span>
                            <span className="ml-2 text-muted-foreground">{c.relation}</span>
                          </span>
                          {c.email ? (
                            <a
                              href={`mailto:${c.email}`}
                              className="inline-flex items-center gap-1.5 font-medium text-primary"
                            >
                              <Mail className="h-3.5 w-3.5" />
                              {c.email}
                            </a>
                          ) : (
                            <span className="text-xs text-muted-foreground">Chưa có email</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="rounded-lg bg-muted/45 p-3">
                  <p className="text-xs font-bold uppercase text-muted-foreground">
                    Vấn đề cần chú ý
                  </p>
                  <p className="mt-1 text-sm font-semibold">{selectedView.problem}</p>
                </div>

                <div className="rounded-lg bg-muted/45 p-3">
                  <p className="text-xs font-bold uppercase text-muted-foreground">
                    Bằng chứng hệ thống
                  </p>
                  <p className="mt-1 text-sm">{selectedView.evidence}</p>
                  <p className="mt-2 text-xs text-muted-foreground">{selectedView.source}</p>
                </div>

                <div className="flex gap-2 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <p>
                    <span className="font-semibold">Gợi ý xử lý: </span>
                    {selectedView.action}
                  </p>
                </div>
              </div>

              {pending ? (
                // Buoc xac nhan - thay CA hang nut de khong con cach nao bam
                // nham sang hanh dong khac khi dang xac nhan.
                <DialogFooter className="flex-col items-stretch gap-2 rounded-lg border border-border bg-muted/40 p-3 sm:flex-col">
                  <p className="text-sm">
                    Chuyển cảnh báo này sang{" "}
                    <span className="font-semibold">{pending.label.toLowerCase()}</span>?
                  </p>
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={() => setPending(null)} disabled={saving}>
                      Huỷ
                    </Button>
                    <Button onClick={xacNhan} disabled={saving}>
                      {saving ? "Đang lưu…" : "Xác nhận"}
                    </Button>
                  </div>
                </DialogFooter>
              ) : (
                <DialogFooter className="gap-2 sm:justify-between">
                  {ACTIONS.filter((a) => a.status === "dismissed").map((a) => (
                    <Button
                      key={a.status}
                      variant={a.variant}
                      className={a.className}
                      disabled={selected.status === a.status}
                      onClick={() => setPending(a)}
                    >
                      {a.label}
                    </Button>
                  ))}
                  <div className="flex gap-2">
                    {ACTIONS.filter((a) => a.status !== "dismissed").map((a) => (
                      <Button
                        key={a.status}
                        variant={a.variant}
                        disabled={selected.status === a.status}
                        onClick={() => setPending(a)}
                      >
                        {a.label}
                      </Button>
                    ))}
                  </div>
                </DialogFooter>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
