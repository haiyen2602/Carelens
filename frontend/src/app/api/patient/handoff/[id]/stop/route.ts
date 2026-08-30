const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const authorization = request.headers.get("authorization");
  const response = await fetch(
    `${BACKEND_URL}/api/v1/agent/v2/handoffs/${encodeURIComponent(id)}/stop`,
    {
      method: "POST",
      headers: authorization ? { Authorization: authorization } : {},
    },
  );
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
