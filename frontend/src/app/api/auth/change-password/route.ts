import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const authHeader = request.headers.get("Authorization");
  if (!authHeader) {
    return NextResponse.json({ detail: "Thiếu Bearer token xác thực" }, { status: 401 });
  }

  const body = await request.json().catch(() => null);
  if (!body?.current_password || !body?.new_password) {
    return NextResponse.json({ detail: "Thiếu mật khẩu hiện tại hoặc mật khẩu mới" }, { status: 400 });
  }

  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/change-password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: authHeader,
    },
    body: JSON.stringify(body),
  });
  const data = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    return NextResponse.json(data ?? { detail: "Đổi mật khẩu thất bại" }, {
      status: backendResponse.status,
    });
  }

  return NextResponse.json(data);
}
