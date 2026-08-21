// Rang buoc chi so co the - FB-08, FB-09.
//
// Mot nguon duy nhat cho ca 3 form nhap (onboarding/profile, doctor/prescribe
// tab suc khoe, doctor/patients). Truoc day moi form tu dat min/max rieng va
// lech nhau: doctor/patients con khong co max nao ca.
//
// PHAI KHOP voi backend/models/schemas.py (CHIEU_CAO_CM_MIN/MAX...). O day chi
// la lop bao truoc de nguoi dung biet ngay tai cho; chan that nam o backend,
// vi min/max cua the <input> bo qua duoc bang DevTools.

/** Chan cung - ngoai khoang nay thi backend tu choi (422). */
export const CHIEU_CAO_CM = { min: 40, max: 250 } as const;
export const CAN_NANG_KG = { min: 2, max: 400 } as const;

/**
 * Canh bao mem - trong chan cung nhung bat thuong.
 *
 * KHONG chan: khoang nay la cua nguoi lon, ma app khong gioi han cho nguoi
 * lon. Chan o day nghia la khong dang ky duoc cho mot dua tre.
 */
const BINH_THUONG_CHIEU_CAO = { min: 140, max: 200 } as const;
const BINH_THUONG_CAN_NANG = { min: 30, max: 150 } as const;

export type KetQuaKiemTra = {
  /** Ngoai chan cung - khong luu duoc. */
  loi: string | null;
  /** Trong chan cung nhung bat thuong - van luu duoc. */
  canhBao: string | null;
};

function kiemTra(
  gia_tri: string,
  chanCung: { min: number; max: number },
  binhThuong: { min: number; max: number },
  ten: string,
  donVi: string,
): KetQuaKiemTra {
  const rong = gia_tri.trim() === "";
  if (rong) return { loi: null, canhBao: null };

  const so = Number(gia_tri);
  if (Number.isNaN(so)) return { loi: `${ten} phải là một số.`, canhBao: null };

  if (so < chanCung.min || so > chanCung.max) {
    return {
      loi: `${ten} phải trong khoảng ${chanCung.min}–${chanCung.max} ${donVi}.`,
      canhBao: null,
    };
  }
  if (so < binhThuong.min || so > binhThuong.max) {
    return {
      loi: null,
      canhBao: `${ten} ${so} ${donVi} khá bất thường — kiểm tra lại giúp mình nhé.`,
    };
  }
  return { loi: null, canhBao: null };
}

export function kiemTraChieuCao(gia_tri: string): KetQuaKiemTra {
  return kiemTra(gia_tri, CHIEU_CAO_CM, BINH_THUONG_CHIEU_CAO, "Chiều cao", "cm");
}

export function kiemTraCanNang(gia_tri: string): KetQuaKiemTra {
  return kiemTra(gia_tri, CAN_NANG_KG, BINH_THUONG_CAN_NANG, "Cân nặng", "kg");
}
