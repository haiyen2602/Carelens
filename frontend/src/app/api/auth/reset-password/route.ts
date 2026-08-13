import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body?.token || !body?.new_password) {
    return NextResponse.json({ detail: "Thiếu mã xác thực hoặc mật khẩu mới" }, { status: 400 });
  }

  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    return NextResponse.json(data ?? { detail: "Đặt lại mật khẩu thất bại" }, {
      status: backendResponse.status,
    });
  }

  return NextResponse.json(data);
}
