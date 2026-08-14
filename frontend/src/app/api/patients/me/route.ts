// Server-side proxy cho GET/PATCH /api/v1/patients/me cua backend that.
//
// File tinh (khong phai [id]/route.ts) de Next.js uu tien dung route nay
// thay vi khop nham vao [id]/route.ts (chi co PATCH, se tra 405 neu khong
// co file rieng nay - phan hoi review 2026-08-14, xem backend/api/
// patient_routes.py::get_my_patient_profile). Backend tu doc patient_id tu
// JWT (current_user.patient_id), khong nhan id tu client.
//
// GET tra PatientSummary (ho so suc khoe co ban - patient/health/page.tsx).
// PATCH tra PatientProfileOut (onboarding "Thong tin ca nhan" - frontend/
// src/app/onboarding/profile/page.tsx) - 2 response shape khac nhau nhung
// cung 1 patient_id, khong xung dot vi khac HTTP method.

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

export async function PATCH(request: Request) {
  const body = await request.text();
  const authorization = request.headers.get("authorization");

  const upstream = await fetch(`${BACKEND_URL}/api/v1/patients/me`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(authorization ? { Authorization: authorization } : {}),
    },
    body,
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
