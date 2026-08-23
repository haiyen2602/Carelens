// Chuan hoa chuoi tieng Viet de so khop khong phan biet dau/hoa-thuong -
// go "nguyen van" van tim duoc "Nguyễn Văn". Cung tinh than voi unaccent()
// ben backend (services/drug_knowledge).
//
// Truoc 2026-08-23 ham nay nam rieng trong components/hover-select.tsx; tach
// ra day khi Hop canh bao (doctor/alerts/page.tsx) can dung cung mot quy tac
// cho o tim kiem benh nhan - hai ban sao lech nhau se cho ket qua tim khac
// nhau giua hai o nhap tren cung mot man hinh.

// NFD tach duoc hau het dau thanh/dau mu, nhung KHONG tach duoc "đ" -
// phai thay tay.
const DAU_KET_HOP = /\p{Diacritic}/gu;

export function boDau(s: string): string {
  return s
    .normalize("NFD")
    .replace(DAU_KET_HOP, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
}
