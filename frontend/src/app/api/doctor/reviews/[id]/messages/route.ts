// Server-side proxy cho POST /api/v1/doctor/reviews/{id}/messages.

import { forwardAuthorization } from "../../authorization";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await request.text();

  const upstream = await fetch(
    `${BACKEND_URL}/api/v1/doctor/reviews/${encodeURIComponent(id)}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...forwardAuthorization(request) },
      body,
    },
  );

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
