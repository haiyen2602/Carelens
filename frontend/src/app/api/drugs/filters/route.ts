// Server-side proxy cho GET /api/v1/drugs/filters — cac gia tri dang_thuoc/
// duong_dung co that trong danh muc, do vao dropdown loc.
//
// Cung ly do ton tai voi app/api/drugs/catalog/route.ts (giu
// X-Internal-Secret phia server). CHI DOC.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

export async function GET() {
  if (!INTERNAL_SECRET) {
    return Response.json(
      { detail: "Server misconfigured: INTERNAL_AUTH_SECRET chua duoc set cho VMEC-04/FE." },
      { status: 500 },
    );
  }

  const upstream = await fetch(`${BACKEND_URL}/api/v1/drugs/filters`, {
    headers: { "X-Internal-Secret": INTERNAL_SECRET },
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
