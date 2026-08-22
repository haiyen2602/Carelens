import { forwardAuthorization } from "../authorization";

// Server-side proxy cho PATCH /api/v1/accounts/{id} (admin).
// Backend xac thuc bang JWT admin; proxy forward nguyen Authorization.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await request.text();
  const upstream = await fetch(`${BACKEND_URL}/api/v1/accounts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...forwardAuthorization(request) },
    body,
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
