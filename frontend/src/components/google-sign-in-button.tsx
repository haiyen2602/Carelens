"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { createClient, isSupabaseConfigured } from "@/lib/supabase";

// Nut "Đăng nhập bằng Google" (Supabase Auth - ADR-0013).
// Su dung supabase.auth.signInWithOAuth de chuyen huong sang Google.
// Callback tro ve /auth/google/callback tren client / route handler.
export function GoogleSignInButton({ label = "Đăng nhập bằng Google" }: { label?: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const click = async () => {
    setError("");
    setLoading(true);

    if (!isSupabaseConfigured) {
      setError(
        "Chưa cấu hình Supabase Auth (NEXT_PUBLIC_SUPABASE_URL & NEXT_PUBLIC_SUPABASE_ANON_KEY).",
      );
      setLoading(false);
      return;
    }

    const supabase = createClient();
    if (!supabase) {
      setError("Không khởi tạo được Supabase Client.");
      setLoading(false);
      return;
    }

    try {
      const redirectTo = `${window.location.origin}/auth/google/callback`;
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo,
          queryParams: {
            prompt: "select_account",
          },
        },
      });

      if (oauthError) {
        throw oauthError;
      }
    } catch (err) {
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
