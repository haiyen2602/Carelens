"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { signInWithGoogle } from "@/lib/better-auth-client";

// Nut "Đăng nhập bằng Google" - dung tren trang dang nhap (app/page.tsx) va
// trang dang ky (app/register/page.tsx). CUNG 1 nut cho ca hai: Google khong
// phan biet "dang nhap" voi "dang ky" - backend tu tao tai khoan `patient` moi
// neu email chua ton tai (xem backend/api/auth_routes.py::oauth_google).
//
// `signInWithGoogle()` chuyen ca trang sang Google, nen `loading` chi de tranh
// bam hai lan trong khoang tre truoc khi trinh duyet roi khoi trang nay.
export function GoogleSignInButton({ label = "Đăng nhập bằng Google" }: { label?: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const click = async () => {
    setError("");
    setLoading(true);
    try {
      await signInWithGoogle();
    } catch (err) {
      // Chi den duoc day khi CHUA roi khoi trang (vd server chua cau hinh
      // GOOGLE_CLIENT_ID -> Better Auth tra loi ngay). Loi phat sinh SAU khi da
      // sang Google se ve /?error=google (errorCallbackURL).
      setError(err instanceof Error ? err.message : "Không mở được đăng nhập Google.");
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="outline"
        size="lg"
        className="w-full"
        onClick={click}
        disabled={loading}
      >
        {/* Logo Google dat inline (khong phai file trong public/): 4 mau thuong
            hieu la co dinh, khong duoc doi theo theme sang/toi cua app. */}
        <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
          <path
            fill="#4285F4"
            d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.46a5.53 5.53 0 0 1-2.4 3.63v3.01h3.88c2.27-2.09 3.58-5.17 3.58-8.83z"
          />
          <path
            fill="#34A853"
            d="M12 24c3.24 0 5.96-1.08 7.94-2.9l-3.88-3.01c-1.08.72-2.45 1.15-4.06 1.15-3.13 0-5.78-2.11-6.73-4.96H1.27v3.12A12 12 0 0 0 12 24z"
          />
          <path
            fill="#FBBC05"
            d="M5.27 14.28a7.2 7.2 0 0 1 0-4.56V6.6H1.27a12 12 0 0 0 0 10.8l4-3.12z"
          />
          <path
            fill="#EA4335"
            d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0A12 12 0 0 0 1.27 6.6l4 3.12C6.22 6.86 8.87 4.75 12 4.75z"
          />
        </svg>
        {loading ? "Đang chuyển tới Google..." : label}
      </Button>
      {error && <p className="text-sm font-medium text-destructive">{error}</p>}
    </div>
  );
}
