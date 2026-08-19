import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { REFRESH_COOKIE_NAME, REFRESH_COOKIE_OPTIONS } from "../login/route";

// DAT mat khau lan dau cho tai khoan tao qua Google (api-contracts.md §1c).
// Giong het ../change-password/route.ts, KHAC DUY NHAT o cho khong co
// `current_password` - backend cho phep vi tai khoan Google chua he co mat
// khau nguoi dung nao (dieu kien `auth_provider == "google"` chi mo duoc 1 lan,
// xem backend/api/auth_routes.py::set_password).
//
// Van phai di qua Route Handler nay (khong goi backend truc tiep tu client):
// response tra ve refresh_token MOI (dat mat khau thu hoi moi token cu), va
// refresh_token chi duoc nam trong httpOnly cookie - JS phia client khong bao
// gio duoc thay no.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const authHeader = request.headers.get("Authorization");
  if (!authHeader) {
    return NextResponse.json({ detail: "Thiếu Bearer token xác thực" }, { status: 401 });
  }

  const body = await request.json().catch(() => null);
  if (!body?.new_password) {
    return NextResponse.json({ detail: "Thiếu mật khẩu mới" }, { status: 400 });
  }

  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/set-password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: authHeader,
    },
    // Chi chuyen tiep `new_password` - khong forward ca body de client khong
    // nhet them field la vao request gui backend.
    body: JSON.stringify({ new_password: body.new_password }),
  });
  const data = await backendResponse.json().catch(() => null);

  if (!backendResponse.ok) {
    return NextResponse.json(data ?? { detail: "Đặt mật khẩu thất bại" }, {
      status: backendResponse.status,
    });
  }

  const { refresh_token: refreshToken, ...clientSafeData } = data;
  const cookieStore = await cookies();
  cookieStore.set(REFRESH_COOKIE_NAME, refreshToken, REFRESH_COOKIE_OPTIONS);

  return NextResponse.json(clientSafeData);
}
