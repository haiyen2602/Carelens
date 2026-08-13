import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body?.token) {
    return NextResponse.json({ detail: "Thiếu mã xác minh" }, { status: 400 });
  }

  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/verify-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    return NextResponse.json(data ?? { detail: "Xác minh thất bại" }, {
      status: backendResponse.status,
    });
  }

  return NextResponse.json(data);
}
