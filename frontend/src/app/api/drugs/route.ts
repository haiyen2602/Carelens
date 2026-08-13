// Server-side proxy cho GET /api/v1/drugs cua backend that.
//
// Cung ly do ton tai voi app/api/chat/route.ts: backend doi header
// `X-Internal-Secret` (rao can tam trong luc cho auth-api - backend/api/
// security.py::require_internal_secret). O tim thuoc nam trong client
// component chay o trinh duyet, gan secret o do thi ai mo tab Network cung
// doc duoc. Route nay chay tren server cua chinh VMEC-04/FE, giu
// INTERNAL_AUTH_SECRET (bien server-only, KHONG co prefix NEXT_PUBLIC_ nen
// khong lot vao bundle) va tu gan header truoc khi forward.
//
// Xoa route nay + goi thang backend voi JWT that khi auth-api xong.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

// Chan tren khop backend (backend/services/drug_knowledge/resolver.py::
// GIOI_HAN_TOI_DA). Xin nhieu hon thi backend tra 422, chan som o day de
// thong bao ro rang hon.
const LIMIT_TOI_DA = 50;

export async function GET(request: Request) {
  if (!INTERNAL_SECRET) {
    // Fail-closed giong nguyen tac backend da dung - khong am tham bo qua rao
    // can chi vi thieu config (xem backend/config.py).
    return Response.json(
      { detail: "Server misconfigured: INTERNAL_AUTH_SECRET chua duoc set cho VMEC-04/FE." },
      { status: 500 },
    );
  }

  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q") ?? "";
  const limit = Math.min(Number(searchParams.get("limit")) || 8, LIMIT_TOI_DA);

  // Tu khoa rong thi khong can di ra toi backend - no cung tra rong.
  if (!q.trim()) {
    return Response.json({ query: q, count: 0, items: [] });
  }

  const upstream = await fetch(
    `${BACKEND_URL}/api/v1/drugs?q=${encodeURIComponent(q)}&limit=${limit}`,
    { headers: { "X-Internal-Secret": INTERNAL_SECRET } },
  );

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
