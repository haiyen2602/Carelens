// Server-side proxy cho POST /api/v1/doses/{id}/photo — gui multipart/form-data.
// Cung ly do ton tai voi app/api/chat/route.ts: backend doi header
// X-Internal-Secret, khong gan duoc o trinh duyet.
//
// Bóc FormData tu request goc roi dung LAI thanh FormData moi, khong forward
// nguyen body/header: fetch tu dat dung Content-Type kem boundary khi body la
// FormData - tu tay ghep lai header multipart de rui ro sai boundary hon nhieu.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!INTERNAL_SECRET) {
    return Response.json(
      { detail: "Server misconfigured: INTERNAL_AUTH_SECRET chua duoc set cho VMEC-04/FE." },
      { status: 500 },
    );
  }

  const { id } = await params;

  const incoming = await request.formData();
  const file = incoming.get("file");
  if (!(file instanceof Blob)) {
    return Response.json({ detail: "Thiếu file ảnh (field 'file')." }, { status: 400 });
  }

  const outgoing = new FormData();
  outgoing.append("file", file, "anh_thuoc.jpg");

  const upstream = await fetch(`${BACKEND_URL}/api/v1/doses/${encodeURIComponent(id)}/photo`, {
    method: "POST",
    headers: { "X-Internal-Secret": INTERNAL_SECRET },
    body: outgoing,
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
