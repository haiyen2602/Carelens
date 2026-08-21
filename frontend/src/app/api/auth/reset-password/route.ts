import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { createServerSupabaseClient, isSupabaseServerConfigured } from "@/lib/supabase-server";
import { REFRESH_COOKIE_NAME, REFRESH_COOKIE_OPTIONS } from "../login/route";

// Endpoint /api/auth/reset-password:
// Nhan request dat lai mat khau moi sau khi nguoi dung nhap mat khau tren trang /auth/reset-password.
// 1. Cap nhat mat khau tren Supabase Auth qua Supabase Server Client
// 2. Goi Backend FastAPI POST /api/v1/auth/reset-password-sync de dong bo vao DB he thong (account.password_hash)

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

export async function POST(req: Request) {
  if (!isSupabaseServerConfigured) {
    return NextResponse.json(
      { detail: "Chưa cấu hình Supabase Auth trên máy chủ" },
      { status: 503 },
    );
  }
  if (!INTERNAL_SECRET) {
    return NextResponse.json(
      { detail: "Server misconfigured: thiếu INTERNAL_AUTH_SECRET" },
      { status: 500 },
    );
  }

  const body = await req.json().catch(() => ({}));
  const { new_password: newPassword, access_token: clientToken, email: clientEmail, provider_account_id: clientUid } = body;

  if (!newPassword || typeof newPassword !== "string" || newPassword.length < 8) {
    return NextResponse.json(
      { detail: "Mật khẩu mới phải có độ dài tối thiểu 8 ký tự" },
      { status: 400 },
    );
  }

  const supabase = await createServerSupabaseClient();

  let email: string | null = clientEmail || null;
  let supabaseUid: string | null = clientUid || null;

  // Lay thong tin user tu token client truyen hoac cookie session
  if (clientToken && (!email || !supabaseUid)) {
    const {
      data: { user },
      error,
    } = await supabase.auth.getUser(clientToken);
    if (!error && user?.email) {
      email = user.email;
      supabaseUid = user.id;
    }
  }

  if (!email || !supabaseUid) {
    const {
      data: { user },
      error,
    } = await supabase.auth.getUser();
    if (!error && user?.email) {
      email = user.email;
      supabaseUid = user.id;
    }
  }

  if (!email || !supabaseUid) {
    return NextResponse.json(
      {
        detail:
          "Phiên đặt lại mật khẩu đã hết hạn hoặc không hợp lệ. Vui lòng yêu cầu lại liên kết.",
      },
      { status: 401 },
    );
  }

  // 1. Client da goi supabase.auth.updateUser() thanh cong truoc khi POST den route nay
  // Khong goi lai supabase.auth.updateUser tren server de tranh loi:
  // "New password should be different from the old password."

  // 2. Dong bo sang Backend FastAPI
  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/reset-password-sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Secret": INTERNAL_SECRET,
    },
    body: JSON.stringify({
      email,
      new_password: newPassword,
      provider_account_id: supabaseUid,
    }),
  }).catch(() => null);

  const data = backendResponse ? await backendResponse.json().catch(() => null) : null;

  if (!backendResponse || !backendResponse.ok) {
    return NextResponse.json(data ?? { detail: "Đồng bộ mật khẩu với hệ thống thất bại" }, {
      status: backendResponse?.status ?? 502,
    });
  }

  // Luu refresh token vao cookie
  const { refresh_token: refreshToken, ...clientSafeData } = data;
  const cookieStore = await cookies();
  cookieStore.set(REFRESH_COOKIE_NAME, refreshToken, REFRESH_COOKIE_OPTIONS);

  return NextResponse.json(clientSafeData);
}
