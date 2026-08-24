import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body?.email || !body?.password || !body?.full_name) {
    return NextResponse.json({ detail: "Thiếu thông tin đăng ký" }, { status: 400 });
  }

  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    return NextResponse.json(data ?? { detail: "Đăng ký thất bại" }, {
      status: backendResponse.status,
    });
  }

  // KHÔNG set refresh_token cookie khi đăng ký vì tài khoản chưa xác thực email
  // (tránh tự động tạo phiên đăng nhập trước khi người dùng nhấp liên kết kích hoạt email).
  const { refresh_token: _refreshToken, ...clientSafeData } = data;

  return NextResponse.json(clientSafeData, { status: 201 });
}

