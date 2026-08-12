// Server-side proxy cho POST /api/v1/chat cua backend that.
//
// TASK-010 (2026-08-13): backend/api/chat_routes.py da bo `X-Internal-Secret`
// (rao tam) va doi sang doi hoi `Authorization: Bearer <JWT>` that
// (backend/api/security.py::get_current_user). Route nay GIO CHI forward
// nguyen header `Authorization` tu client (trinh duyet, qua useAuth() -
// xem frontend/src/lib/auth.tsx) sang backend, KHONG con tu gan
// X-Internal-Secret nua - backend tu tra 401 neu thieu/sai/het han JWT,
// khong can route nay tu kiem tra truoc.
//
// Van giu route proxy nay (khong goi thang backend tu client) de tuong lai
// de doi sang forward qua httpOnly cookie/refresh-on-401 ma khong dong vao
// component goi chat - xem cung pattern o frontend/src/app/api/auth/*.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const body = await request.text();
  const authorization = request.headers.get("authorization");

  const upstream = await fetch(`${BACKEND_URL}/api/v1/chat`, {
    method: "POST",
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
