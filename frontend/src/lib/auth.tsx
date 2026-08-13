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

// TASK-010 (auth-api that, api-contracts.md §1) - thay the admin-auth.ts
// (flag localStorage gia). access_token chi giu trong memory (React state)
// - KHONG localStorage (tranh XSS doc duoc token). refresh_token la httpOnly
// cookie do Route Handler (app/api/auth/*) quan ly - JS o day khong bao gio
// dong cham truc tiep vao refresh_token.
export type AuthUser = { id: string; full_name: string; role: string };

type AuthState = {
  user: AuthUser | null;
  accessToken: string | null;
  loading: boolean;
};

type RegisterData = {
  full_name: string;
  email: string;
  password: string;
  role?: string;
};

type AuthContextValue = AuthState & {
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (data: { full_name: string; email: string; password: string; role?: string }) => Promise<AuthUser>;
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
          setState({ user: data.user, accessToken: data.access_token, loading: false });
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
    setState({ user: data.user, accessToken: data.access_token, loading: false });
    return data.user as AuthUser;
  }, []);

  const register = useCallback(async (payload: { full_name: string; email: string; password: string; role?: string }) => {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(data?.detail ?? "Đăng ký thất bại");
    }
    setState({ user: data.user, accessToken: data.access_token, loading: false });
    return data.user as AuthUser;
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    setState({ user: null, accessToken: null, loading: false });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, register, logout }),
    [state, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() phải dùng bên trong <AuthProvider>");
  return ctx;
}
