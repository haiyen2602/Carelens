// Proxy STT that -- cung mau voi app/api/drug-images/recognize/route.ts
// (forward FormData nguyen ven, khong tu gan Content-Type de fetch tu dung
// boundary; forward header Authorization nguyen ven, khong tu kiem tra
// truoc, backend tu tra 401/403 dung thiet ke).

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return Response.json(
      { detail: { code: "INVALID_MULTIPART", message: "Dữ liệu ghi âm gửi lên không hợp lệ." } },
      { status: 400 },
    );
  }
  const authorization = request.headers.get("authorization");
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/api/v1/voice/transcribe`, {
      method: "POST",
      headers: authorization ? { Authorization: authorization } : undefined,
      body: form,
    });
  } catch {
    return Response.json(
      { detail: "Không thể nhận diện giọng nói lúc này. Bạn vẫn có thể gõ tin nhắn." },
      { status: 503 },
    );
  }
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
