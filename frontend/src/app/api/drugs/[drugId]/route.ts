// Server-side proxy cho GET /api/v1/drugs/{drug_id} cua backend that.
//
// Cung ly do ton tai voi app/api/drugs/route.ts: backend doi header
// `X-Internal-Secret`, khong the gan o trinh duyet. Route nay chay tren server
// cua FE, giu INTERNAL_AUTH_SECRET (server-only) va tu gan header truoc khi
// forward.
//
// CHI DOC - khong co POST/PATCH/DELETE o day, trang tra cuu thuoc cua bac si
// khong sua duoc danh muc.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

export async function GET(_request: Request, { params }: { params: Promise<{ drugId: string }> }) {
  if (!INTERNAL_SECRET) {
    // Fail-closed giong app/api/drugs/route.ts - khong am tham bo qua rao can
    // chi vi thieu config.
    return Response.json(
      { detail: "Server misconfigured: INTERNAL_AUTH_SECRET chua duoc set cho VMEC-04/FE." },
      { status: 500 },
    );
  }

  const { drugId } = await params;
  const upstream = await fetch(`${BACKEND_URL}/api/v1/drugs/${encodeURIComponent(drugId)}`, {
    headers: { "X-Internal-Secret": INTERNAL_SECRET },
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
