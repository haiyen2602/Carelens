"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { request } from "@/lib/api";

// TASK-010 (auth-api that, api-contracts.md §1) - thay the admin-auth.ts
// (flag localStorage gia). access_token chi giu trong memory (React state)
// - KHONG localStorage (tranh XSS doc duoc token). refresh_token la httpOnly
// cookie do Route Handler (app/api/auth/*) quan ly - JS o day khong bao gio
// dong cham truc tiep vao refresh_token.
export type AuthUser = {
  id: string;
  full_name: string;
  role: string;
  patient_id: string | null;
  doctor_id: string | null;
};

// `/auth/login` (UserOut) CO Y chi tra id/full_name/role dung field mau
// api-contracts.md §1 - khong sua schema do. patient_id/doctor_id lay rieng
// tu /auth/me (MeResponse, da co san 2 truong nay) ngay sau khi dang nhap/
// khoi phuc phien, goi thang backend kem Bearer token - cung pattern voi
// lib/accounts.ts (khong lien quan cookie nen khong can qua Route Handler).
async function layLienKet(accessToken: string): Promise<Pick<AuthUser, "patient_id" | "doctor_id">> {
  const me = await request<{ patient_id: string | null; doctor_id: string | null }>(
    "/api/v1/auth/me",
    { headers: { Authorization: `Bearer ${accessToken}` } },
  );
  return { patient_id: me.patient_id, doctor_id: me.doctor_id };
}

type AuthState = {
  user: AuthUser | null;
  accessToken: string | null;
  loading: boolean;
};

type AuthContextValue = AuthState & {
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, accessToken: null, loading: true });

  useEffect(() => {
    // Khoi phuc phien luc tai trang (F5) - access_token trong memory da mat,
    // nhung refresh_token (httpOnly cookie) van con qua duoc reload. Goi
    // /api/auth/refresh 1 lan luc mount - im lang neu chua tung dang nhap
    // (401 la binh thuong, khong phai loi can bao).
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/refresh", { method: "POST" });
        if (!cancelled && res.ok) {
          const data = await res.json();
          const lienKet = await layLienKet(data.access_token);
          if (!cancelled) {
            setState({
              user: { ...data.user, ...lienKet },
              accessToken: data.access_token,
              loading: false,
            });
          }
          return;
        }
      } catch {
        // Mat mang/backend down luc khoi phuc phien - coi nhu chua dang nhap,
        // khong chan UI.
      }
      if (!cancelled) setState({ user: null, accessToken: null, loading: false });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(data?.detail ?? "Đăng nhập thất bại");
    }
    const lienKet = await layLienKet(data.access_token);
    const user: AuthUser = { ...data.user, ...lienKet };
    setState({ user, accessToken: data.access_token, loading: false });
    return user;
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    setState({ user: null, accessToken: null, loading: false });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, logout }),
    [state, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() phải dùng bên trong <AuthProvider>");
  return ctx;
}
