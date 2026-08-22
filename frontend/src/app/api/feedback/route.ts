// Server-side proxy cho BUILD-29's "Báo cáo câu trả lời" - cung mau voi
// app/api/chat/route.ts: chi forward nguyen header Authorization tu client
// sang backend that (POST /api/v1/agent/v2/feedback), KHONG tu kiem tra
// role/patient_id o day - backend tu tra 403/429 dung thiet ke neu sai
// role, trace khong thuoc ve tai khoan nay, hoac vuot rate limit.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const body = await request.text();
  const authorization = request.headers.get("authorization");

  const upstream = await fetch(`${BACKEND_URL}/api/v1/agent/v2/feedback`, {
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
