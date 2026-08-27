const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return Response.json(
      { detail: { code: "INVALID_MULTIPART", message: "Du lieu anh gui len khong hop le." } },
      { status: 400 },
    );
  }
  const authorization = request.headers.get("authorization");
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/api/v1/agent/v2/drug-images/recognize`, {
      method: "POST",
      // Do not set Content-Type: fetch creates the multipart boundary while
      // preserving the actual File bytes, filename and MIME type in `form`.
      headers: authorization ? { Authorization: authorization } : undefined,
      body: form,
    });
  } catch {
    return Response.json(
      { detail: { code: "RECOGNITION_UPSTREAM_UNAVAILABLE", message: "Khong the xu ly anh luc nay. Hay thu lai sau." } },
      { status: 503 },
    );
  }
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
