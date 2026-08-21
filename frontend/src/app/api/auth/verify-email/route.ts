import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { createServerSupabaseClient, isSupabaseServerConfigured } from "@/lib/supabase-server";
import { REFRESH_COOKIE_NAME, REFRESH_COOKIE_OPTIONS } from "../login/route";

// Endpoint /api/auth/verify-email:
// Nhan request xac minh email sau khi nguoi dung nhap link trong email hoac code duoc trao doi.
// 1. Doc thong tin user tu Supabase Auth (server-side)
// 2. Goi Backend FastAPI POST /api/v1/auth/verify-email-sync de kich hoat is_email_verified = True

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

  const authHeader = req.headers.get("Authorization");
  const body = await req.json().catch(() => ({}));
  const clientToken = authHeader?.toLowerCase().startsWith("bearer ")
    ? authHeader.split(" ", 2)[1]
    : body?.access_token;

  const supabase = await createServerSupabaseClient();

  let email: string | null = null;
  let supabaseUid: string | null = null;
  let fullName: string | null = null;

  if (clientToken) {
    const {
      data: { user },
      error,
    } = await supabase.auth.getUser(clientToken);
    if (!error && user?.email) {
      email = user.email;
      supabaseUid = user.id;
      fullName = (user.user_metadata?.full_name as string | undefined) ?? null;
    }
  }

  if (!email) {
    const {
      data: { user },
      error,
    } = await supabase.auth.getUser();
    if (!error && user?.email) {
      email = user.email;
      supabaseUid = user.id;
      fullName = fullName ?? ((user.user_metadata?.full_name as string | undefined) ?? null);
    }
  }

  if (!email || !supabaseUid) {
    return NextResponse.json(
      { detail: "Phiên xác minh email không hợp lệ hoặc đã hết hạn." },
      { status: 401 },
    );
  }

  // Dong bo trang thai xac minh sang Backend FastAPI
  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/verify-email-sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Secret": INTERNAL_SECRET,
    },
    body: JSON.stringify({
      email,
      provider_account_id: supabaseUid,
      // Truyen full_name de backend upsert Account neu chua ton tai
      ...(fullName ? { full_name: fullName } : {}),
    }),
  }).catch(() => null);

  const data = backendResponse ? await backendResponse.json().catch(() => null) : null;

  if (!backendResponse || !backendResponse.ok) {
    return NextResponse.json(data ?? { detail: "Kích hoạt tài khoản thất bại" }, {
      status: backendResponse?.status ?? 502,
    });
  }

  // Luu refresh token vao cookie
  const { refresh_token: refreshToken, ...clientSafeData } = data;
  const cookieStore = await cookies();
  cookieStore.set(REFRESH_COOKIE_NAME, refreshToken, REFRESH_COOKIE_OPTIONS);

  return NextResponse.json(clientSafeData);
}
