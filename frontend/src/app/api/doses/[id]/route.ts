// Server-side proxy cho PATCH /api/v1/doses/{id}.
//
// Backend doi hoi Authorization: Bearer <JWT> that (get_current_user, xem
// backend/api/dose_routes.py::update_dose_status) - CHUA forward header nay
// (chi gan X-Internal-Secret) nen truoc gio chua the goi thanh cong, phat
// hien khi xay tinh nang nguoi than duyet lieu (patient/family/[id]/page.tsx).
// Sua theo dung pattern app/api/chat/route.ts.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await request.text();
  const authorization = request.headers.get("authorization");

  const upstream = await fetch(`${BACKEND_URL}/api/v1/doses/${id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(authorization ? { Authorization: authorization } : {}),
    },
    body,
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
