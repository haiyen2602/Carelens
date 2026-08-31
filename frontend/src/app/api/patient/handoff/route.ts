import { NextRequest } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const response = await fetch(
    `${BACKEND_URL}/api/v1/agent/v2/handoff/status${request.nextUrl.search}`,
    {
      headers: request.headers.get("authorization")
        ? { Authorization: request.headers.get("authorization")! }
        : {},
    },
  );
  return new Response(await response.text(), {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
