// Server-side proxy cho GET /api/v1/reporting/patients cua backend that.
//
// Backend doi hoi Authorization: Bearer <JWT> that (require_role, xem
// backend/api/reporting_routes.py::list_reporting_patients) - khong con
// X-Internal-Secret nua (doi boi PR khac merge cung luc voi PR them trang
// nay, phat hien 2026-08-13 qua log production tra 401). Forward header tu
// request cua trinh duyet, cung pattern voi app/api/doses/[id]/route.ts.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: Request) {
  const authorization = request.headers.get("authorization");
  const search = new URL(request.url).searchParams.get("search");
  const qs = search ? `?search=${encodeURIComponent(search)}` : "";

  const upstream = await fetch(`${BACKEND_URL}/api/v1/reporting/patients${qs}`, {
    headers: { ...(authorization ? { Authorization: authorization } : {}) },
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
