// Server-side proxy cho PATCH /api/v1/patients/{id}.
//
// Backend doi hoi Authorization: Bearer <JWT> that (require_role, xem
// backend/api/patient_routes.py::update_patient_health) - khong con
// X-Internal-Secret nua, xem ghi chu day du o app/api/reporting/patients/route.ts.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await request.text();
  const authorization = request.headers.get("authorization");

  const upstream = await fetch(`${BACKEND_URL}/api/v1/patients/${id}`, {
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
