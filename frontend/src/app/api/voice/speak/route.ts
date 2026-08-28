// Proxy TTS that -- KHAC voi cac proxy JSON khac trong thu muc nay: response
// tra ve la BINARY (audio/mpeg), khong duoc .text()/JSON hoa lai, phai giu
// nguyen upstream.body de trinh duyet phat duoc am thanh.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const body = await request.text();
  const authorization = request.headers.get("authorization");
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/api/v1/voice/speak`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authorization ? { Authorization: authorization } : {}),
      },
      body,
    });
  } catch {
    return Response.json({ detail: "Không thể đọc câu trả lời lúc này." }, { status: 503 });
  }

  if (!upstream.ok) {
    const errorBody = await upstream.text();
    return new Response(errorBody, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "audio/mpeg" },
  });
}
