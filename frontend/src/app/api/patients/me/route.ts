// Server-side proxy cho GET /api/v1/patients/me cua backend that.
//
// File tinh (khong phai [id]/route.ts) de Next.js uu tien dung route nay
// thay vi khop nham vao [id]/route.ts (chi co PATCH, se tra 405 neu khong
// co file rieng nay - phan hoi review 2026-08-14, xem backend/api/
// patient_routes.py::get_my_patient_profile). Backend tu doc patient_id tu
// JWT (current_user.patient_id), khong nhan id tu client - dung Authorization
// header that giong cac route patients khac.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: Request) {
  const authorization = request.headers.get("authorization");

  const upstream = await fetch(`${BACKEND_URL}/api/v1/patients/me`, {
    headers: { ...(authorization ? { Authorization: authorization } : {}) },
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
