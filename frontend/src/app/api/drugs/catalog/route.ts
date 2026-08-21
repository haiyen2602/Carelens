// Server-side proxy cho GET /api/v1/drugs/catalog (duyet danh muc + loc +
// phan trang) va /api/v1/drugs/filters.
//
// Cung ly do ton tai voi app/api/drugs/route.ts: backend doi header
// `X-Internal-Secret`, khong gan duoc o trinh duyet.
//
// CHI DOC. Phai nam o thu muc `catalog/` rieng chu khong gop vao
// `[drugId]/route.ts`: Next se coi "catalog" la mot drugId va forward sai.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

// Khop chan tren cua backend (GIOI_HAN_TOI_DA).
const LIMIT_TOI_DA = 50;

export async function GET(request: Request) {
  if (!INTERNAL_SECRET) {
    return Response.json(
      { detail: "Server misconfigured: INTERNAL_AUTH_SECRET chua duoc set cho VMEC-04/FE." },
      { status: 500 },
    );
  }

  const { searchParams } = new URL(request.url);
  const query = new URLSearchParams();
  query.set("q", searchParams.get("q") ?? "");
  query.set("limit", String(Math.min(Number(searchParams.get("limit")) || 20, LIMIT_TOI_DA)));
  query.set("offset", String(Math.max(Number(searchParams.get("offset")) || 0, 0)));

  const dangThuoc = searchParams.get("dang_thuoc");
  if (dangThuoc) query.set("dang_thuoc", dangThuoc);
  const duongDung = searchParams.get("duong_dung");
  if (duongDung) query.set("duong_dung", duongDung);

  const upstream = await fetch(`${BACKEND_URL}/api/v1/drugs/catalog?${query.toString()}`, {
    headers: { "X-Internal-Secret": INTERNAL_SECRET },
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
