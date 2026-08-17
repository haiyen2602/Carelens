import { cookies, headers } from "next/headers";
import { NextResponse } from "next/server";

import { auth, googleAuthConfigured } from "@/lib/better-auth";
import { REFRESH_COOKIE_NAME, REFRESH_COOKIE_OPTIONS } from "../login/route";

// "Login with Google" - CAU NOI giua Better Auth (moi gioi OAuth) va auth that
// cua he thong (JWT cua backend FastAPI).
//
// Luong day du:
//   1. Client bam nut -> authClient.signIn.social({provider:"google"})
//   2. Google xac thuc -> GET /api/better-auth/callback/google
//      Better Auth tao 1 phien CUA RIENG NO (cookie) + ban ghi ba_user/ba_account
//   3. Trinh duyet toi /auth/google/callback -> trang do goi POST route nay
//   4. Route nay doc phien Better Auth (server-side), lay email+name da xac
//      thuc, goi POST /api/v1/auth/oauth/google -> nhan LoginResponse that
//   5. refresh_token -> httpOnly cookie (giong /api/auth/login), phien Better
//      Auth bi HUY -> tu day tro di he thong chi con 1 khai niem dang nhap
//
// Vi sao khong de Better Auth lam luon phien dang nhap: 40 route backend doc
// role/patient_id tu JWT cua chinh no (backend/api/security.py), va toan bo
// RBAC (khoa tai khoan, thu hoi token khi doi mat khau) nam trong bang
// `account`. Chuyen sang phien Better Auth se phai viet lai tat ca nhung thu do.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const INTERNAL_SECRET = process.env.INTERNAL_AUTH_SECRET;

export async function POST() {
  if (!googleAuthConfigured) {
    return NextResponse.json(
      { detail: "Đăng nhập bằng Google chưa được cấu hình trên máy chủ" },
      { status: 503 },
    );
  }
  if (!INTERNAL_SECRET) {
    // POST /api/v1/auth/oauth/google duoc chan bang X-Internal-Secret (khong
    // public - xem ghi chu trong backend/api/auth_routes.py::oauth_google).
    // Thieu secret o phia nay thi backend se tra 401 - bao loi ro rang o day de
    // khong phai di doan tu 401 cua backend.
    return NextResponse.json(
      { detail: "Server misconfigured: thiếu INTERNAL_AUTH_SECRET" },
      { status: 500 },
    );
  }

  // Doc phien Better Auth NGAY TREN SERVER (khong tin bat ky gia tri nao tu
  // body request): day la diem duy nhat chung minh "Google da xac thuc nguoi
  // nay". Neu doc email tu body do client gui, ai cung POST duoc mot email tuy
  // y vao day va nhan lai JWT cua chu email do.
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session?.user?.email) {
    return NextResponse.json({ detail: "Chưa xác thực với Google" }, { status: 401 });
  }

  // `accountId` cua provider = `sub` cua Google (dinh danh on dinh, khong doi
  // khi nguoi dung doi email). Doc tu bang ba_account - KHONG co trong session.
  const accounts = await auth.api.listUserAccounts({ headers: await headers() }).catch(() => null);
  const googleAccountId =
    accounts?.find((a: { providerId: string; accountId: string }) => a.providerId === "google")
      ?.accountId ?? session.user.id;

  const backendResponse = await fetch(`${API_BASE}/api/v1/auth/oauth/google`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Secret": INTERNAL_SECRET,
    },
    body: JSON.stringify({
      email: session.user.email,
      // Google khong bat buoc tra `name`; roi ve phan truoc @ cua email de
      // backend khong tu choi vi full_name rong (min_length=1).
      full_name: session.user.name?.trim() || session.user.email.split("@")[0],
      provider_account_id: googleAccountId,
      email_verified: session.user.emailVerified,
    }),
  }).catch(() => null);
  const data = backendResponse ? await backendResponse.json().catch(() => null) : null;

  // SUA 2026-08-17 (loi that gap tren localhost): KHONG huy phien Better Auth
  // khi backend loi ha tang (mat mang / container backend cu chua co route ->
  // 404 / 5xx). Truoc day route nay signOut vo dieu kien, nen bug that (404 vi
  // backend chua rebuild) hien ra o lan thu 2 duoi dang 401 "Chưa xác thực với
  // Google" - hoan toan sai huong, va nguoi dung buoc phai lam lai ca vong
  // OAuth cho moi lan thu.
  //
  // Van huy phien khi backend TU CHOI danh tinh (4xx khac 404: tai khoan bi
  // khoa, email Google chua xac thuc): thu lai khong bao gio doi ket qua, va
  // khong duoc de mot phien song song ton tai lau cho tai khoan da bi khoa.
  const backendRejectedIdentity =
    backendResponse !== null &&
    !backendResponse.ok &&
    backendResponse.status >= 400 &&
    backendResponse.status < 500 &&
    backendResponse.status !== 404;
  if (!backendResponse || backendResponse.ok || backendRejectedIdentity) {
    await auth.api.signOut({ headers: await headers() }).catch(() => undefined);
  }

  if (!backendResponse) {
    return NextResponse.json(
      { detail: "Không kết nối được tới máy chủ để hoàn tất đăng nhập bằng Google" },
      { status: 502 },
    );
  }

  if (!backendResponse.ok) {
    // 404 = backend dang chay CHUA co POST /api/v1/auth/oauth/google (container
    // cu chua rebuild). Noi thang ra thay vi de nguyen "Not Found" chung chung.
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

  // Tu day giong het /api/auth/login: refresh_token vao httpOnly cookie (JS
  // client khong doc duoc - han che rui ro XSS), access_token tra ve body cho
  // client giu trong memory (lib/auth.tsx).
  const { refresh_token: refreshToken, ...clientSafeData } = data;
  const cookieStore = await cookies();
  cookieStore.set(REFRESH_COOKIE_NAME, refreshToken, REFRESH_COOKIE_OPTIONS);

  return NextResponse.json(clientSafeData);
}
