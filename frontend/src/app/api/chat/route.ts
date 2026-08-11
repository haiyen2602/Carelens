// Server-side proxy cho POST /api/v1/chat cua backend that.
//
// Vi sao co route nay thay vi frontend goi thang backend: backend dang doi
// header `X-Internal-Secret` (rao can tam - chatbot-rag-design.md muc 10 #10,
// backend/api/security.py::require_internal_secret) trong luc cho auth-api
// (JWT) that duoc xay. Trang chat (`patient/assistant/page.tsx`) la client
// component chay trong trinh duyet - neu gan secret o do, bat ky ai mo
// DevTools/Network tab cung doc duoc, pha vo hoan toan muc dich cua rao can.
// Route nay chay tren server cua chinh VMEC-04/FE, giu `INTERNAL_AUTH_SECRET`
// (bien server-only, KHONG co prefix NEXT_PUBLIC_ nen khong lot vao bundle
// gui ve trinh duyet) va tu gan header truoc khi forward request that sang
// backend. Xoa route nay + gan thang tu backend that (JWT) khi auth-api xong.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

export async function POST(request: Request) {
  if (!INTERNAL_SECRET) {
    // Fail-closed giong nguyen tac backend da dung (khong am tham bo qua rao
    // can chi vi thieu config) - xem backend/config.py.
    return Response.json(
      { detail: "Server misconfigured: INTERNAL_AUTH_SECRET chua duoc set cho VMEC-04/FE." },
      { status: 500 },
    );
  }

  const body = await request.text();

  const upstream = await fetch(`${BACKEND_URL}/api/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Secret": INTERNAL_SECRET,
    },
    body,
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
