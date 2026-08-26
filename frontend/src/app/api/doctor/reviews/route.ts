// Server-side proxy cho GET /api/v1/doctor/reviews cua backend that (BUILD-44
// Doctor Chat Queue & Takeover). Cung quy uoc voi app/api/patients/route.ts -
// chuyen tiep Authorization: Bearer <JWT> that, khong tu them logic auth o day
// (backend tu kiem require_role("doctor") + require_active_doctor).

import { forwardAuthorization } from "./authorization";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const qs = url.search; // status / handoff_type / assigned_to_me - chuyen nguyen ve backend, khong tu dien giai o day.

  const upstream = await fetch(`${BACKEND_URL}/api/v1/doctor/reviews${qs}`, {
    headers: forwardAuthorization(request),
  });

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
