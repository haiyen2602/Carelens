// Server-side proxy cho GET /api/v1/photo-verifications/{id}/image.
// KHAC cac route khac trong thu muc nay: response la anh nhi phan (JPEG),
// khong phai JSON - forward nguyen bytes + content-type thay vi doc .text().

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!INTERNAL_SECRET) {
    return Response.json(
      { detail: "Server misconfigured: INTERNAL_AUTH_SECRET chua duoc set cho VMEC-04/FE." },
      { status: 500 },
    );
  }

  const { id } = await params;
  const upstream = await fetch(
    `${BACKEND_URL}/api/v1/photo-verifications/${encodeURIComponent(id)}/image`,
    { headers: { "X-Internal-Secret": INTERNAL_SECRET } },
  );

  if (!upstream.ok) {
    const data = await upstream.text();
    return new Response(data, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "image/jpeg" },
  });
}
