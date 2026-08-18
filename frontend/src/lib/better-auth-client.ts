"use client";

import { createAuthClient } from "better-auth/react";

// Client cua Better Auth - CHI dung de bat dau luong OAuth Google
// (`signIn.social`). KHONG dung `useSession()` cua Better Auth o bat ky dau
// trong app: phien dang nhap that la useAuth() (frontend/src/lib/auth.tsx,
// JWT cua backend). Phien Better Auth bi huy ngay sau khi doi lay JWT, nen
// useSession() se luon rong va gay hieu nham neu ai do dung toi.
//
// `basePath` PHAI khop voi cau hinh server (lib/better-auth.ts) - mac dinh cua
// thu vien la /api/auth, cho do da bi cac Route Handler cua du an chiem.
export const authClient = createAuthClient({
  basePath: "/api/better-auth",
});

/** Bat dau luong "Đăng nhập bằng Google".
 *
 * `callbackURL` la noi Google/Better Auth tra nguoi dung ve SAU khi xac thuc
 * xong: mot trang trung gian cua chinh du an (`/auth/google/callback`) - trang
 * do goi `/api/auth/google-bridge` de doi phien Better Auth thanh JWT that roi
 * moi dieu huong vao /patient|/doctor|/admin. KHONG tra thang ve "/" duoc: luc
 * do useAuth() chua he biet gi ve nguoi vua dang nhap.
 *
 * `errorCallbackURL`: Google/Better Auth that bai (nguoi dung bam Huy, sai cau
 * hinh...) -> ve thang trang dang nhap kem ?error= de hien thong bao, thay vi
 * bo nguoi dung o mot trang loi trang cua thu vien.
 */
export function signInWithGoogle() {
  return authClient.signIn.social({
    provider: "google",
    callbackURL: "/auth/google/callback",
    errorCallbackURL: "/?error=google",
  });
}
