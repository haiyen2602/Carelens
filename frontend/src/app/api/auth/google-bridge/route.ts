import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { createServerSupabaseClient, isSupabaseServerConfigured } from "@/lib/supabase-server";
import { REFRESH_COOKIE_NAME, REFRESH_COOKIE_OPTIONS } from "../login/route";

// "Login with Google" (Supabase Auth - ADR-0013)
// CAU NOI giua Supabase Auth (moi gioi OAuth) va auth that cua he thong (JWT cua backend FastAPI).
//
// Luong day du:
//   1. Client bam nut -> supabase.auth.signInWithOAuth({ provider: "google" })
//   2. Google -> Supabase -> callback ve frontend /auth/google/callback
//   3. Client trao doi code hoac session, gui session/token hoac route handler doc session tu Supabase Server Client
//   4. Route handler goi POST /api/v1/auth/oauth/google voi thong tin da xac thuc
//   5. refresh_token -> httpOnly cookie (giong /api/auth/login), access_token tra ve cho client giu trong memory (lib/auth.tsx)

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

export async function POST(req: Request) {
  if (!isSupabaseServerConfigured) {
    return NextResponse.json(
      { detail: "Đăng nhập bằng Google (Supabase Auth) chưa được cấu hình trên máy chủ" },
      { status: 503 },
    );
  }
  if (!INTERNAL_SECRET) {
    return NextResponse.json(
      { detail: "Server misconfigured: thiếu INTERNAL_AUTH_SECRET" },
      { status: 500 },
    );
  }

  let email: string | null = null;
  let fullName: string | null = null;
  let supabaseUid: string | null = null;
  let emailVerified = false;

  // Thu 1: Kiem tra access_token duoc truyen truc tiep tu client (PKCE / implicit flow)
  const authHeader = req.headers.get("Authorization");
  const body = await req.json().catch(() => ({}));

  const clientToken = authHeader?.toLowerCase().startsWith("bearer ")
    ? authHeader.split(" ", 2)[1]
    : body?.access_token;

  const supabase = await createServerSupabaseClient();

  if (clientToken) {
    const {
      data: { user },
      error,
    } = await supabase.auth.getUser(clientToken);
    if (!error && user?.email) {
      email = user.email;
      fullName =
        (user.user_metadata?.full_name as string) || (user.user_metadata?.name as string) || null;
      supabaseUid = user.id;
      emailVerified = Boolean(
        user.email_confirmed_at || user.confirmed_at || user.app_metadata?.provider === "google",
      );
    }
  }

  // Thu 2: Neu khong co client token, doc session tu cookie cua Supabase Server Client
  if (!email) {
    const {
      data: { user },
      error,
    } = await supabase.auth.getUser();
    if (!error && user?.email) {
      email = user.email;
      fullName =
        (user.user_metadata?.full_name as string) || (user.user_metadata?.name as string) || null;
      supabaseUid = user.id;
      emailVerified = Boolean(
        user.email_confirmed_at || user.confirmed_at || user.app_metadata?.provider === "google",
      );
    }
  }

  if (!email || !supabaseUid) {
    return NextResponse.json({ detail: "Chưa xác thực với Google / Supabase" }, { status: 401 });
  }

  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/oauth/google`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Secret": INTERNAL_SECRET,
    },
    body: JSON.stringify({
      email,
      full_name: fullName?.trim() || email.split("@")[0],
      provider_account_id: supabaseUid,
      email_verified: emailVerified,
    }),
  }).catch(() => null);

  const data = backendResponse ? await backendResponse.json().catch(() => null) : null;

  if (!backendResponse) {
    return NextResponse.json(
      { detail: "Không kết nối được tới máy chủ để hoàn tất đăng nhập bằng Google" },
      { status: 502 },
    );
  }

  if (!backendResponse.ok) {
    if (backendResponse.status === 404) {
      return NextResponse.json(
        { detail: "Backend chưa có endpoint /auth/oauth/google (cần rebuild/restart backend)" },
        { status: 502 },
      );
    }
    return NextResponse.json(data ?? { detail: "Đăng nhập bằng Google thất bại" }, {
      status: backendResponse.status,
    });
  }

  // Luu refresh_token vao httpOnly cookie, access_token tra ve cho client giu trong memory
  const { refresh_token: refreshToken, ...clientSafeData } = data;
  const cookieStore = await cookies();
  cookieStore.set(REFRESH_COOKIE_NAME, refreshToken, REFRESH_COOKIE_OPTIONS);

  return NextResponse.json(clientSafeData);
}
