// Server-side proxy cho GET /api/v1/patients cua backend that.
//
// Backend doi hoi Authorization: Bearer <JWT> that (require_role, xem
// backend/api/patient_routes.py::list_patients) - khong con X-Internal-Secret
// nua, xem ghi chu day du o app/api/reporting/patients/route.ts.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: Request) {
  const authorization = request.headers.get("authorization");
  const search = new URL(request.url).searchParams.get("search");
  const qs = search ? `?search=${encodeURIComponent(search)}` : "";

  const upstream = await fetch(`${BACKEND_URL}/api/v1/patients${qs}`, {
    headers: { ...(authorization ? { Authorization: authorization } : {}) },
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
