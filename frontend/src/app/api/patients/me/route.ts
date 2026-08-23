// Server-side proxy cho GET/PATCH /api/v1/patients/me cua backend that.
//
// File tinh (khong phai [id]/route.ts) de Next.js uu tien dung route nay
// thay vi khop nham vao [id]/route.ts (chi co PATCH, se tra 405 neu khong
// co file rieng nay - phan hoi review 2026-08-14, xem backend/api/
// patient_routes.py::get_my_patient_profile). Backend tu doc patient_id tu
// JWT (current_user.patient_id), khong nhan id tu client.
//
// GET va PATCH deu tra PatientProfileOut (SUA 2026-08-23: GET tung tra
// PatientSummary, thieu phone/address/date_of_birth nen man hinh "Doi thong
// tin ca nhan" - frontend/src/components/edit-personal-info-dialog.tsx -
// khong do lai duoc du lieu hien co, xem backend/api/patient_routes.py::
// get_my_patient_profile). Dung cho ca patient/health/page.tsx (chi doc
// full_name/year_of_birth) lan onboarding/profile/page.tsx + dialog doi
// thong tin ca nhan.

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
