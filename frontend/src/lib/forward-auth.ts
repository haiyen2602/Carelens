// Dung trong cac route proxy o app/api/* (chay tren server cua Next).
//
// Cac endpoint phac do ben backend van gac bang X-Internal-Secret va nhan
// doctor_id tu body (hien la hang so `demo-doctor-01`, xem lib/prescriptions.ts)
// nen ban than chung KHONG biet bac si nao vua bam nut. Chuyen tiep them
// Authorization: Bearer cua nguoi dung de backend doc duoc danh tinh THAT qua
// get_optional_current_user() va ghi dung ten vao nhat ky thao tac
// (SystemAuditLog) - xem backend/api/prescription_routes.py::_ghi_nhat_ky.
//
// KHONG thay doi quyen: backend van chi chap nhan request nho X-Internal-
// Secret, token o day thuan tuy de quy trach nhiem thao tac. Thieu token thi
// request van chay binh thuong, chi khong co dong nhat ky.
export function kemAuthNeuCo(
  request: Request,
  headers: Record<string, string>,
): Record<string, string> {
  const authorization = request.headers.get("authorization");
  return authorization ? { ...headers, Authorization: authorization } : headers;
}
