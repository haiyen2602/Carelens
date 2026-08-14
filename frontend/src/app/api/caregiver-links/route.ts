// Server-side proxy cho GET/POST /api/v1/caregiver-links cua backend that.
// Cung ly do ton tai voi app/api/chat/route.ts: backend doi header
// X-Internal-Secret, khong gan duoc o trinh duyet.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

function thieuSecret() {
  return Response.json(
    { detail: "Server misconfigured: INTERNAL_AUTH_SECRET chua duoc set cho VMEC-04/FE." },
    { status: 500 },
  );
}

export async function GET(request: Request) {
  if (!INTERNAL_SECRET) return thieuSecret();

  const { search } = new URL(request.url);
  const upstream = await fetch(`${BACKEND_URL}/api/v1/caregiver-links${search}`, {
    headers: { "X-Internal-Secret": INTERNAL_SECRET },
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function POST(request: Request) {
  if (!INTERNAL_SECRET) return thieuSecret();

  const body = await request.text();
  const upstream = await fetch(`${BACKEND_URL}/api/v1/caregiver-links`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Internal-Secret": INTERNAL_SECRET },
    body,
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
