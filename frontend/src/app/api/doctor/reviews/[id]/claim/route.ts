// Server-side proxy cho POST /api/v1/doctor/reviews/{id}/claim.

import { forwardAuthorization } from "../../authorization";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const upstream = await fetch(
    `${BACKEND_URL}/api/v1/doctor/reviews/${encodeURIComponent(id)}/claim`,
    {
      method: "POST",
      headers: forwardAuthorization(request),
    },
  );

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
