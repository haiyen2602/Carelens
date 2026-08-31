"use client";

// Tab "Lịch sử" - port tu capyphone.js::renderHistory(), noi voi lich su
// lieu thuoc THAT.
//
// Ban mau hard-code "92%", "23/25 lieu", "🔥 7 ngay lien tiep" va 7 o mau
// co dinh. O day moi con so deu tinh tu `doses` that; bo phan "chuoi ngay
// lien tiep" vi chua co gi tinh duoc no. Dai pill "7 ngay/Hom nay/30 ngay"
// la bo loc that chu khong phai trang tri.

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { DoseHistoryDialog } from "@/components/dose-history-dialog";
import { CHIP, CHIP_THEO_TRANG_THAI, PillChip, SectionLabel } from "@/components/capy/capy-ui";
import { useAuth } from "@/lib/auth";
import { gioHienThi, listDoses, ngayHienThi, type Dose } from "@/lib/doses";

const KHOANG = [
  { key: "today", label: "Hôm nay", days: 1 },
  { key: "week", label: "7 ngày", days: 7 },
  { key: "month", label: "30 ngày", days: 30 },
] as const;
type KhoangKey = (typeof KHOANG)[number]["key"];

const TEN_THU = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

// Nhat ky mo ra chi 5 dong. Danh sach day du cua mot benh nhan that dai toi
// 127 dong sau khi job chot lieu qua han chay - do khong con la "lich su" ma
// la mot buc tuong. Moi lan bam "Xem them" mo them 20 dong, cung khong do het
// mot luc.
const SO_DONG_BAN_DAU = 5;
const SO_DONG_MOI_LAN_MO = 20;

// Trang thai bi loai khoi PHEP TINH TUAN THU (khong phai khoi danh sach):
//   - AWAITING_CAREGIVER: dang cho NGUOI THAN duyet sau khi anh khong khop 3
//     lan. Benh nhan da lam phan cua ho; tinh la bo lieu se phat nham nguoi.
//     Duoc dem rieng thanh dong "N lieu cho nguoi than duyet".
//   - CANCELLED: phac do da dung, khong noi len dieu gi ve viec uong thuoc.
// Cung tap voi backend/api/reporting_routes.py::_TRANG_THAI_VAO_MAU_SO.
const NGOAI_MAU_SO = ["AWAITING_CAREGIVER", "CANCELLED"];

function khoaNgay(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

// So sanh theo NGAY-THANG cuc bo (khong phai epoch ms so voi "now"): mot
// lieu "hom nay 08:00 gio VN" luu UTC co the la moc UTC con o TUONG LAI so
// voi "now" ngay sau nua dem VN (UTC+7) du da duoc ghi TAKEN that trong
// ngay - so sanh epoch se loai nham lieu do khoi khoang.
function trongKhoang(iso: string, days: number): boolean {
  const d = new Date(iso);
  const nay = new Date();
  const dNgay = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const nayNgay = new Date(nay.getFullYear(), nay.getMonth(), nay.getDate()).getTime();
  const cach = Math.round((nayNgay - dNgay) / 86400000);
  return cach >= 0 && cach < days;
}

// "Da den han" la moc THUC (epoch), khong phai moc ngay nhu trongKhoang(): mot
// lieu chi vao mau so khi cua so xac nhan cua no da dong. Cung dinh nghia voi
// backend/services/reporting/adherence.py::compute_adherence_pct().
function daDenHan(d: Dose): boolean {
  return new Date(d.windowEnd).getTime() <= Date.now();
}

function tenThuoc(d: Dose): string {
  return d.expectedItems.map((i) => i.tenThuoc).join(", ") || "Thuốc";
}

export default function HistoryPage() {
  const { user } = useAuth();
  const patientId = user?.patient_id ?? "";
  // allDoses: TOAN BO lich - dung cho thong ke + bieu do 7 ngay. Khong loc
  // san o day: lieu MISSED khong co anh se bien mat khoi bieu do thay vi
  // hien do.
  const [allDoses, setAllDoses] = useState<Dose[]>([]);
  const [dangTai, setDangTai] = useState(true);
  const [dangXem, setDangXem] = useState<Dose | null>(null);
  const [khoang, setKhoang] = useState<KhoangKey>("today");
  const [soDongHien, setSoDongHien] = useState(SO_DONG_BAN_DAU);

  useEffect(() => {
    if (!patientId) return;
    setDangTai(true);
    // `has_photo` di kem ngay trong GET /doses (backend/api/dose_routes.py
    // ::_dose_ids_co_anh). Truoc 2026-08-31 cho nay goi listPhotoVerifications()
    // cho TUNG lieu - 147 request HTTP moi lan mo trang, de biet mot dieu ma
    // ca DB chi co 42 dong photo_verification. Vong lap do con chay tren TOAN
    // BO lieu chu khong phai lieu dang xem, nen tab "Hom nay" hien 2 dong
    // cung van ban du 147 request.
    listDoses(patientId)
      .then(setAllDoses)
      .catch((err) => toast.error(err instanceof Error ? err.message : "Không tải được lịch sử"))
      .finally(() => setDangTai(false));
  }, [patientId]);

  const soNgay = KHOANG.find((k) => k.key === khoang)!.days;

  // Doi bo loc thi thu gon lai: vua chuyen sang "30 ngay" ma van giu 60 dong
  // dang mo cua lan truoc thi khong con la thu gon nua.
  useEffect(() => {
    setSoDongHien(SO_DONG_BAN_DAU);
  }, [khoang]);

  // Danh sach hien thi: moi lieu DA DEN HAN trong khoang, ke ca
  // AWAITING_CAREGIVER va PENDING qua han. Chung khong vao phep tinh tuan thu
  // nhung van la mot dong lich su that - va truoc day danh sach co chung con
  // thong ke thi khong, nen khong ai cong tay ra duoc con so tren the tong ket.
  const danhSach = useMemo(
    () =>
      allDoses
        .filter((d) => trongKhoang(d.scheduledAt, soNgay) && daDenHan(d))
        .sort((a, b) => b.scheduledAt.localeCompare(a.scheduledAt)),
    [allDoses, soNgay],
  );

  const tongKet = useMemo(() => {
    // MAU SO = moi lieu DA DEN HAN, khong phai chi nhung lieu da co ket qua.
    // Truoc 2026-08-31 cho nay loc ["TAKEN","DELAYED","MISSED"], nen lieu benh
    // nhan khong dung toi (con PENDING du da qua han) bien mat khoi CA tu so
    // lan mau so - im lang duoc thuong. Do tren du lieu that: hien 88% (29/33)
    // trong khi thuc te la 29/127.
    const denHan = danhSach;
    const trongMauSo = denHan.filter((d) => !NGOAI_MAU_SO.includes(d.status));
    const uong = trongMauSo.filter((d) => d.status === "TAKEN" || d.status === "DELAYED").length;
    return {
      coDuLieu: trongMauSo.length > 0,
      pct: trongMauSo.length > 0 ? Math.round((uong / trongMauSo.length) * 100) : 0,
      uong,
      tong: trongMauSo.length,
      muon: trongMauSo.filter((d) => d.status === "DELAYED").length,
      bo: trongMauSo.filter((d) => d.status === "MISSED").length,
      choNguoiThan: denHan.filter((d) => d.status === "AWAITING_CAREGIVER").length,
    };
  }, [danhSach]);

  // Gom theo ngay: truoc day moi dong deu lap lai "28/08/2026" o dong phu du
  // ca man hinh cung mot ngay. Dua ngay len tieu de nhom lam danh sach ngan
  // lai ma khong phai giau bot du lieu nao.
  const nhomTheoNgay = useMemo(() => {
    const nhom: { ngay: string; lieu: Dose[] }[] = [];
    for (const d of danhSach.slice(0, soDongHien)) {
      const nhan = ngayHienThi(d.scheduledAt);
      const cuoi = nhom[nhom.length - 1];
      if (cuoi && cuoi.ngay === nhan) cuoi.lieu.push(d);
      else nhom.push({ ngay: nhan, lieu: [d] });
    }
    return nhom;
  }, [danhSach, soDongHien]);

  const conLai = danhSach.length - soDongHien;

  // 7 o = 7 ngay gan nhat, mau theo trang thai GOP cua ngay (khong phai cot
  // cao thap - dung dung cach cua ban thiet ke: 1 mau / 1 o).
  const bieuDo = useMemo(() => {
    const homNay = new Date();
    const o: { key: string; thu: string; mau: string; fg: string }[] = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(homNay);
      d.setDate(d.getDate() - i);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      const lieu = allDoses.filter((x) => khoaNgay(x.scheduledAt) === key);
      let mau = "#B7CBE8";
      let fg = "#2F5488";
      if (lieu.some((x) => x.status === "MISSED")) {
        mau = "#B4432C";
        fg = "#fff";
      } else if (lieu.some((x) => x.status === "DELAYED")) {
        mau = "#E39A16";
        fg = "#fff";
      } else if (lieu.length > 0 && lieu.every((x) => x.status === "TAKEN")) {
        mau = "#2E9E6B";
        fg = "#fff";
      }
      o.push({ key, thu: TEN_THU[d.getDay()], mau, fg });
    }
    return o;
  }, [allDoses]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display m-0 mt-1 text-[30px] font-extrabold leading-[1.1] text-[#16386E]">
        Lịch sử
      </h1>

      <div className="flex gap-2">
        {KHOANG.map((k) => (
          <button
            key={k.key}
            onClick={() => setKhoang(k.key)}
            className="rounded-full px-[15px] py-[9px] text-[13px] font-semibold transition-colors"
            style={
              khoang === k.key
                ? { background: "#16386E", color: "#fff" }
                : { background: "#fff", color: "#5B6A85" }
            }
          >
            {k.label}
          </button>
        ))}
      </div>

      {/* The tong ket */}
      {!dangTai && tongKet.coDuLieu && (
        <div className="rounded-[28px] bg-[#CFE6FF] p-5">
          <p className="font-display m-0 text-[40px] font-extrabold leading-none text-[#16386E]">
            {tongKet.pct}%
          </p>
          <p className="m-0 mt-1.5 text-[14px] font-semibold text-[#2F5488]">
            {tongKet.uong} / {tongKet.tong} liều đã hoàn thành
          </p>
          <p className="m-0 mt-0.5 text-[13px] text-[#3D5D8C]">
            {tongKet.muon} lần xác nhận muộn • {tongKet.bo} liều bỏ qua
          </p>
          {/* Chi hien khi that su co lieu dang cho - mot con so luon bang 0
              chi lam the tong ket day them mot dong vo nghia. */}
          {tongKet.choNguoiThan > 0 && (
            <p className="m-0 mt-0.5 text-[13px] text-[#3D5D8C]">
              {tongKet.choNguoiThan} liều chờ người thân duyệt
            </p>
          )}
          <div className="mt-4 grid grid-cols-7 gap-1.5">
            {bieuDo.map((o) => (
              <span
                key={o.key}
                className="font-mono grid h-[52px] items-end justify-center rounded-[12px] pb-1 text-[9px] font-medium"
                style={{ background: o.mau, color: o.fg }}
              >
                {o.thu}
              </span>
            ))}
          </div>
        </div>
      )}

      {dangTai && (
        <div className="flex items-center justify-center gap-2 rounded-[24px] bg-white p-6 text-[13px] text-[#5B6A85]">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải lịch sử…
        </div>
      )}

      {/* Danh sach lieu */}
      {!dangTai && (
        <div>
          <div className="mb-2.5">
            <SectionLabel>Nhật ký liều thuốc</SectionLabel>
          </div>
          {danhSach.length === 0 ? (
            <div className="rounded-[24px] bg-white p-6 text-center text-[13px] text-[#5B6A85]">
              Chưa có liều nào trong khoảng này.
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {nhomTheoNgay.map((nhom) => (
                <div key={nhom.ngay}>
                  <p className="font-mono m-0 mb-1 px-1 text-[11px] font-medium text-[#62708A]">
                    {nhom.ngay}
                  </p>
                  <div className="overflow-hidden rounded-[24px] bg-white">
                    {nhom.lieu.map((d, i) => (
                      <button
                        key={d.id}
                        onClick={() => setDangXem(d)}
                        className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2.5 px-4 py-[15px] text-left transition-colors hover:bg-[#FAFBFE]"
                        style={{
                          borderBottom: i === nhom.lieu.length - 1 ? "none" : "1px solid #EDF0F6",
                        }}
                      >
                        <span className="block min-w-0">
                          <span
                            className="block truncate text-[14px] font-semibold"
                            title={`${ngayHienThi(d.scheduledAt)} · ${gioHienThi(d.scheduledAt)} · ${tenThuoc(d)}`}
                          >
                            {gioHienThi(d.scheduledAt)} — {tenThuoc(d)}
                          </span>
                          <span className="font-mono block text-[11px] text-[#62708A]">
                            {d.hasPhoto ? "xác nhận bằng ảnh" : "không có ảnh"}
                          </span>
                        </span>
                        <PillChip chip={CHIP_THEO_TRANG_THAI[d.status] ?? CHIP.upcoming} />
                      </button>
                    ))}
                  </div>
                </div>
              ))}

              {conLai > 0 ? (
                <button
                  onClick={() => setSoDongHien((n) => n + SO_DONG_MOI_LAN_MO)}
                  className="rounded-[20px] bg-white px-4 py-3 text-[13px] font-semibold text-[#2F5488] transition-colors hover:bg-[#FAFBFE]"
                >
                  Xem thêm {conLai} liều
                </button>
              ) : (
                danhSach.length > SO_DONG_BAN_DAU && (
                  <button
                    onClick={() => setSoDongHien(SO_DONG_BAN_DAU)}
                    className="rounded-[20px] bg-white px-4 py-3 text-[13px] font-semibold text-[#5B6A85] transition-colors hover:bg-[#FAFBFE]"
                  >
                    Thu gọn
                  </button>
                )
              )}
            </div>
          )}
        </div>
      )}

      <DoseHistoryDialog
        dose={dangXem}
        open={dangXem !== null}
        onOpenChange={(o) => {
          if (!o) setDangXem(null);
        }}
      />
    </div>
  );
}
