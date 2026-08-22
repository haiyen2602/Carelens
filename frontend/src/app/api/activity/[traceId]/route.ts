// BUILD-30: server-side proxy cho "Xem hoạt động" - cung mau voi
// app/api/chat/route.ts va app/api/feedback/route.ts: chi forward nguyen
// header Authorization sang backend that (GET /api/v1/agent/v2/traces/
// {traceId}/activity), KHONG tu kiem tra role/patient_id o day - backend tu
// tra 403 (cross-patient/khong phai patient) hoac 200 voi available:false
// (trace khong con snapshot) dung thiet ke neu sai.

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: Request, { params }: { params: Promise<{ traceId: string }> }) {
  const { traceId } = await params;
  const authorization = request.headers.get("authorization");

  const upstream = await fetch(
    `${BACKEND_URL}/api/v1/agent/v2/traces/${encodeURIComponent(traceId)}/activity`,
    {
      headers: {
        ...(authorization ? { Authorization: authorization } : {}),
      },
    },
  );

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
