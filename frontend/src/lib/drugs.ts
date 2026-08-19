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
export async function searchDrugs(query: string, signal?: AbortSignal, limit = 8): Promise<Drug[]> {
  if (!query.trim()) return [];

  const response = await fetch(`/api/drugs?q=${encodeURIComponent(query)}&limit=${limit}`, {
    signal,
  });
  if (!response.ok) {
    throw new Error(`Tra cứu thuốc thất bại (${response.status})`);
  }

  const data: { items: DrugApiItem[] } = await response.json();
  return (data.items ?? []).map(toDrug);
}

// Duyet danh muc cho trang tra cuu (doctor/drugs): tu khoa RONG tra ve trang
// dau cua ca danh muc, khac searchDrugs() o tren.
export async function browseDrugs(
  params: {
    q?: string;
    dangThuoc?: string;
    duongDung?: string;
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal,
): Promise<{ total: number; items: Drug[] }> {
  const query = new URLSearchParams();
  query.set("q", params.q ?? "");
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  if (params.dangThuoc) query.set("dang_thuoc", params.dangThuoc);
  if (params.duongDung) query.set("duong_dung", params.duongDung);

  const response = await fetch(`/api/drugs/catalog?${query.toString()}`, { signal });
  if (!response.ok) {
    throw new Error(`Tra cứu thuốc thất bại (${response.status})`);
  }

  const data: { total: number; items: DrugApiItem[] } = await response.json();
  return { total: data.total ?? 0, items: (data.items ?? []).map(toDrug) };
}

/** Gia tri co that cua dang_thuoc/duong_dung, do vao dropdown loc. */
export async function getDrugFilters(
  signal?: AbortSignal,
): Promise<{ dangThuoc: string[]; duongDung: string[] }> {
  const response = await fetch("/api/drugs/filters", { signal });
  if (!response.ok) {
    throw new Error(`Không tải được bộ lọc (${response.status})`);
  }

  const data: { dang_thuoc: string[]; duong_dung: string[] } = await response.json();
  return { dangThuoc: data.dang_thuoc ?? [], duongDung: data.duong_dung ?? [] };
}

// Chi tiet mot thuoc, cho trang tra cuu cua bac si (doctor/drugs). Them phan
// van ban mo ta so voi `Drug` - 4 truong nay lay tu drug_chunks va co the
// null vi moi 226/3562 thuoc da duoc embed.
export type DrugDetail = Drug & {
  danhMuc: string | null;
  congDung: string | null;
  tacDungPhu: string | null;
  cachDung: string | null;
  baoQuan: string | null;
};

type DrugDetailApiItem = DrugApiItem & {
  danh_muc: string | null;
  cong_dung: string | null;
  tac_dung_phu: string | null;
  cach_dung: string | null;
  bao_quan: string | null;
};

/** Lay chi tiet 1 thuoc theo id. `null` neu khong co trong danh muc. */
export async function getDrugDetail(
  drugId: string,
  signal?: AbortSignal,
): Promise<DrugDetail | null> {
  const response = await fetch(`/api/drugs/${encodeURIComponent(drugId)}`, { signal });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Không tải được chi tiết thuốc (${response.status})`);
  }

  const item: DrugDetailApiItem = await response.json();
  return {
    ...toDrug(item),
    danhMuc: item.danh_muc,
    congDung: item.cong_dung,
    tacDungPhu: item.tac_dung_phu,
    cachDung: item.cach_dung,
    baoQuan: item.bao_quan,
  };
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
