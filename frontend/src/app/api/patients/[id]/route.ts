// Server-side proxy cho PATCH /api/v1/patients/{id}.
// Cung ly do ton tai voi app/api/chat/route.ts.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!INTERNAL_SECRET) {
    return Response.json(
      { detail: "Server misconfigured: INTERNAL_AUTH_SECRET chua duoc set cho VMEC-04/FE." },
      { status: 500 },
    );
  }

  const { id } = await params;
  const body = await request.text();
  const upstream = await fetch(`${BACKEND_URL}/api/v1/patients/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", "X-Internal-Secret": INTERNAL_SECRET },
    body,
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
