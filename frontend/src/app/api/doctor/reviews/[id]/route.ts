// Server-side proxy cho GET /api/v1/doctor/reviews/{id} (chi tiet 1 handoff +
// luong tin nhan). Cung quy uoc voi app/api/patients/route.ts.

import { forwardAuthorization } from "../authorization";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const upstream = await fetch(`${BACKEND_URL}/api/v1/doctor/reviews/${encodeURIComponent(id)}`, {
    headers: forwardAuthorization(request),
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
