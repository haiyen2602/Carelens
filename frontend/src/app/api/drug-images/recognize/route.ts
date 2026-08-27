const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const form = await request.formData();
  const authorization = request.headers.get("authorization");
  const upstream = await fetch(`${BACKEND_URL}/api/v1/agent/v2/drug-images/recognize`, {
    method: "POST",
    headers: authorization ? { Authorization: authorization } : undefined,
    body: form,
  });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
