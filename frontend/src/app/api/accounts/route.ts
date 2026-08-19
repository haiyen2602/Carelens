import { forwardAuthorization } from "./authorization";

// Server-side proxy cho GET/POST /api/v1/accounts cua backend that (admin).
// Backend xac thuc bang JWT admin; proxy forward nguyen Authorization.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: Request) {
  const upstream = await fetch(`${BACKEND_URL}/api/v1/accounts`, {
    headers: forwardAuthorization(request),
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function POST(request: Request) {
  const body = await request.text();
  const upstream = await fetch(`${BACKEND_URL}/api/v1/accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...forwardAuthorization(request) },
    body,
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
