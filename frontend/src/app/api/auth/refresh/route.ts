import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { REFRESH_COOKIE_NAME } from "../login/route";

// TASK-010 - doc refresh_token tu httpOnly cookie (client khong doc duoc
// truc tiep), goi backend /auth/refresh, roi luu lai refresh_token MOI vao
// cookie (rotation). Dung de khoi phuc phien sau khi reload trang - access
// token trong memory (frontend/src/lib/auth.ts) mat khi reload, nhung
// cookie nay van con.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST() {
  const cookieStore = await cookies();
  const refreshToken = cookieStore.get(REFRESH_COOKIE_NAME)?.value;
  if (!refreshToken) {
    return NextResponse.json({ detail: "Chưa đăng nhập" }, { status: 401 });
  }

  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  const data = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    cookieStore.delete(REFRESH_COOKIE_NAME);
    return NextResponse.json(data ?? { detail: "Phiên đăng nhập đã hết hạn" }, {
      status: backendResponse.status,
    });
  }

  const { refresh_token: newRefreshToken, ...clientSafeData } = data;
  cookieStore.set(REFRESH_COOKIE_NAME, newRefreshToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/api/auth",
  });

  return NextResponse.json(clientSafeData);
}
