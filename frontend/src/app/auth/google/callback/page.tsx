"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { createClient } from "@/lib/supabase";
import { useAuth } from "@/lib/auth";
import { useProto } from "@/lib/proto-store";

// Trang trung gian cua luong "Đăng nhập bằng Google" (Supabase Auth - ADR-0013)
// Noi Google va Supabase tra nguoi dung ve voi access_token / code.
//
// Luong: Trang nay lay session tu Supabase client, goi loginWithGoogle(supabaseAccessToken)
// de doi lay JWT he thong qua /api/auth/google-bridge, nap vao useAuth() va dieu huong.
export default function GoogleCallbackPage() {
  const router = useRouter();
  const { loginWithGoogle } = useAuth();
  const { login: protoLogin, pushActivity } = useProto();
  const [error, setError] = useState("");
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    (async () => {
      try {
        const supabase = createClient();
        let token: string | undefined;

        if (supabase) {
          // Kiem tra session tu Supabase client hoac URL hash (PKCE / implicit)
          const {
            data: { session },
            error: sessionError,
          } = await supabase.auth.getSession();
          if (sessionError) {
            console.warn("Supabase getSession error:", sessionError);
          }
          if (session?.access_token) {
            token = session.access_token;
          }
        }

        const user = await loginWithGoogle(token);

        if (user.role === "doctor" || user.role === "patient") {
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
  }, [loginWithGoogle, protoLogin, pushActivity, router]);

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
