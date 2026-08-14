// Server-side proxy cho GET/PATCH /api/v1/patients/me - trang onboarding
// "Thong tin ca nhan" (frontend/src/app/onboarding/profile/page.tsx). Cung
// pattern voi app/api/patients/[id]/route.ts: chi forward Authorization,
// backend tu suy patient_id tu JWT (khong tin id tu client).

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: Request) {
  const authorization = request.headers.get("authorization");

  const upstream = await fetch(`${BACKEND_URL}/api/v1/patients/me`, {
    headers: {
      ...(authorization ? { Authorization: authorization } : {}),
    },
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
