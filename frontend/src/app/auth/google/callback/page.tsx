"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

// Trang trung gian cua luong "Đăng nhập bằng Google" - noi Google/Better Auth
// tra nguoi dung ve (callbackURL trong lib/better-auth-client.ts).
//
// Vi sao can trang nay thay vi tra thang ve "/": luc Google tra ve, phien duy
// nhat dang ton tai la phien CUA BETTER AUTH - useAuth() (JWT that) chua biet
// gi. Trang nay goi /api/auth/google-bridge de doi lay JWT, nap vao useAuth()
// qua updateSession(), roi moi dieu huong theo role. Nguoi dung chi thay 1
// man hinh "Đang hoàn tất..." trong khoang 1 giay.
export default function GoogleCallbackPage() {
  const router = useRouter();
  const { loginWithGoogle } = useAuth();
  const { login: protoLogin, pushActivity } = useProto();
  const [error, setError] = useState("");
  // React 18+ o che do dev goi useEffect HAI LAN. Doi lay JWT khong idempotent
  // (moi lan la 1 cap token moi) va no HUY phien Better Auth - lan 2 se that
  // bai voi 401 va day nguoi dung ve trang loi du lan 1 da thanh cong.
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    (async () => {
      try {
        const user = await loginWithGoogle();

        if (user.role === "doctor" || user.role === "patient") {
          // Cau noi TAM giong trang dang nhap (app/page.tsx): dashboard
          // doctor/patient con dung state cua proto-store cho header/banner.
          protoLogin(user.role, user.full_name);
          pushActivity("Đăng nhập thành công", `Chào mừng trở lại, ${user.full_name}.`);
          if (user.role === "patient" && user.profile_completed === false) {
            router.replace("/onboarding/profile");
          } else {
            router.replace(user.role === "doctor" ? "/doctor" : "/patient");
          }
        } else if (user.role === "admin") {
          router.replace("/admin");
        } else {
          setError("Vai trò người thân/caregiver chưa được hỗ trợ trên giao diện web.");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Đăng nhập bằng Google thất bại.");
      }
    })();
    // loginWithGoogle/protoLogin/pushActivity deu la useCallback on dinh; ranRef
    // da chan chay lai nen khong can chung trong deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="grid min-h-screen place-items-center bg-background px-6">
      <div className="flex max-w-sm flex-col items-center gap-3 text-center">
        <Image
          src="/logo-capymedi-v2.png"
          alt="CapyMedi"
          width={48}
          height={48}
          className={`h-12 w-12 ${error ? "" : "animate-pulse"}`}
          priority
        />
        {error ? (
          <>
            <p className="text-sm font-medium text-destructive">{error}</p>
            <a href="/" className="text-sm font-semibold text-primary hover:underline">
              Quay lại trang đăng nhập
            </a>
          </>
        ) : (
          <p className="text-sm font-medium text-muted-foreground">
            Đang hoàn tất đăng nhập bằng Google...
          </p>
        )}
      </div>
    </div>
  );
}
