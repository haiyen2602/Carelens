// Tra cuu thuoc tu danh muc THAT (3562 thuoc, bang `drug` trong Postgres).
//
// Truoc day file nay la mot mang 19 thuoc viet cung. Van de khong phai o so
// luong ma o cho: mang do khong co `dang_thuoc`. Ma dang bao che la thu quyet
// dinh mot lieu thuoc co xac minh duoc bang anh hay khong (backend/services/
// photo_verification/dosage_form.py) - khong co no thi don thuoc ke ra khong
// biet la vien nen hay lo siro, va luong chup anh xac nhan khong co gi de doi
// chieu.
//
// Goi qua /api/drugs (route handler cua chinh FE) chu khong goi thang backend:
// backend doi header X-Internal-Secret, khong the gan o trinh duyet.

export type Drug = {
  drugId: string;
  tenThuoc: string;
  dangThuoc: string;
  duongDung: string;
  hamLuong: string | null;
  tongSoLuong: string | null;
  mucNghiemTrong: string | null;
};

type DrugApiItem = {
  drug_id: string;
  ten_thuoc: string;
  dang_thuoc: string;
  duong_dung: string;
  ham_luong: string | null;
  tong_so_luong: string | null;
  muc_nghiem_trong: string | null;
};

function toDrug(item: DrugApiItem): Drug {
  return {
    drugId: item.drug_id,
    tenThuoc: item.ten_thuoc,
    dangThuoc: item.dang_thuoc,
    duongDung: item.duong_dung,
    hamLuong: item.ham_luong,
    tongSoLuong: item.tong_so_luong,
    mucNghiemTrong: item.muc_nghiem_trong,
  };
}

/**
 * Tim thuoc theo ten. Tu khoa rong tra ve rong (khong tai ca 3562 thuoc).
 *
 * `signal` de huy request cu khi nguoi dung go tiep - khong co no thi ket qua
 * ve khong dung thu tu se ghi de len nhau, o goi y nhay lung tung.
 */
export async function searchDrugs(query: string, signal?: AbortSignal): Promise<Drug[]> {
  if (!query.trim()) return [];

  const response = await fetch(`/api/drugs?q=${encodeURIComponent(query)}&limit=8`, { signal });
  if (!response.ok) {
    throw new Error(`Tra cứu thuốc thất bại (${response.status})`);
  }

  const data: { items: DrugApiItem[] } = await response.json();
  return (data.items ?? []).map(toDrug);
}

/** Dong mo ta duoi ten thuoc trong o goi y: "Viên nén · 500mg". */
export function moTaThuoc(drug: Drug): string {
  return [drug.dangThuoc, drug.hamLuong].filter(Boolean).join(" · ");
}

// Don vi goi y theo dang bao che, chi de dien san o "Lieu dung" cho bac si
// khoi phai go tu dau. KHONG phai nguon su that: bac si sua duoc, va viec xac
// dinh don vi that de doi chieu anh nam o backend (services/photo_verification/
// dosage_form.py) chu khong o day.
const DON_VI_GOI_Y: [RegExp, string][] = [
  [/viên/i, "1 viên"],
  [/gói|bột|cốm/i, "1 gói"],
  [/siro|dung dịch uống|hỗn dịch/i, "10 ml"],
  [/kem|gel|mỡ|thuốc mỡ/i, "1 lần bôi"],
  [/tiêm|truyền/i, "1 ống"],
];

/** Goi y lieu dung ban dau khi bac si chon mot thuoc tu danh muc. */
export function goiYLieu(drug: Drug): string {
  const khop = DON_VI_GOI_Y.find(([mau]) => mau.test(drug.dangThuoc));
  return khop ? khop[1] : "1 liều";
}
