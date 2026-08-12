import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

// TASK-010 (auth-api that, api-contracts.md §1) - Route Handler nay dong
// vai tro BFF proxy: goi thang backend that (server-side, khong lo domain
// backend cho client), roi tach `refresh_token` ra khoi response de luu
// vao httpOnly cookie (JS phia client KHONG doc duoc - han che rui ro XSS
// danh cap refresh token). `access_token` van tra ve body cho client giu
// trong memory (xem frontend/src/lib/auth.ts).
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const REFRESH_COOKIE_NAME = "capymedi_refresh_token";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body?.email || !body?.password) {
    return NextResponse.json({ detail: "Thiếu email hoặc mật khẩu" }, { status: 400 });
  }

  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    return NextResponse.json(data ?? { detail: "Đăng nhập thất bại" }, {
      status: backendResponse.status,
    });
  }

  const { refresh_token: refreshToken, ...clientSafeData } = data;
  const cookieStore = await cookies();
  cookieStore.set(REFRESH_COOKIE_NAME, refreshToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/api/auth",
  });

  return NextResponse.json(clientSafeData);
}
