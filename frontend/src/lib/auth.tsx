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
  // THEM (migration 0022) - chi co y nghia khi role="patient" (frontend
  // dung de bat buoc redirect sang /onboarding/profile). null cho role khac.
  profile_completed: boolean | null;
  // Lay tu /auth/me (MeResponse co field nay, /auth/login UserOut thi
  // khong) - optional vi chi co sau khi layLienKet() chay xong.
  email?: string;
  // THEM (migration 0025) - "google" = tai khoan tao qua Login with Google,
  // CHUA co mat khau nguoi dung nao. UI dung de hien "Đặt mật khẩu"
  // (/api/auth/set-password) thay vi "Đổi mật khẩu" - hoi mat khau hien tai
  // cua mot thu khong ton tai thi nguoi dung se ngoi thu lai vo ich.
  auth_provider: string;
};

// `/auth/login` (UserOut) CO Y chi tra id/full_name/role dung field mau
// api-contracts.md §1 - khong sua schema do. patient_id/doctor_id/
// profile_completed lay rieng tu /auth/me (MeResponse, da co san cac
// truong nay) ngay sau khi dang nhap/khoi phuc phien, goi thang backend
// kem Bearer token - cung pattern voi lib/accounts.ts (khong lien quan
// cookie nen khong can qua Route Handler).
async function layLienKet(
  accessToken: string,
): Promise<
  Pick<AuthUser, "patient_id" | "doctor_id" | "profile_completed" | "email" | "auth_provider">
> {
  const me = await request<{
    email: string;
    patient_id: string | null;
    doctor_id: string | null;
    profile_completed: boolean | null;
    auth_provider: string;
  }>("/api/v1/auth/me", { headers: { Authorization: `Bearer ${accessToken}` } });
  return {
    email: me.email,
    patient_id: me.patient_id,
    doctor_id: me.doctor_id,
    profile_completed: me.profile_completed,
    // Backend cu (chua co migration 0025) khong tra truong nay - mac dinh
    // "password" de UI khong bao gio nham tuong tai khoan thuong la tai khoan
    // Google roi an mat nut doi mat khau cua ho.
    auth_provider: me.auth_provider ?? "password",
  };
}

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
  provider_account_id?: string;
};

type AuthContextValue = AuthState & {
  login: (email: string, password: string) => Promise<AuthUser>;
  loginWithGoogle: (supabaseAccessToken?: string) => Promise<AuthUser>;
  register: (data: RegisterData) => Promise<AuthUser>;
  logout: () => Promise<void>;
  updateSession: (accessToken: string, user: AuthUser) => void;
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
      // Dang ky/dang nhap co the DA hoan tat trong luc request khoi phuc dang
      // bay (ro nhat o /auth/google/callback: trang do goi loginWithGoogle()
      // ngay khi mount, song song voi /api/auth/refresh o day - refresh tra 401
      // vi chua he co cookie, va neu ghi de vo dieu kien thi phien Google vua
      // lay duoc se bi xoa). Chi ghi "chua dang nhap" khi that su chua co ai.
      if (!cancelled) {
        setState((prev) =>
          prev.user
            ? { ...prev, loading: false }
            : { user: null, accessToken: null, loading: false },
        );
      }
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

  // "Login with Google" (Supabase Auth - ADR-0013)
  // Buoc cuoi cua luong OAuth sau khi Supabase redirect ve /auth/google/callback.
  // Trang callback goi ham nay (co the truyen session token cua Supabase) de
  // doi lay JWT backend thong qua route /api/auth/google-bridge.
  const loginWithGoogle = useCallback(async (supabaseAccessToken?: string) => {
    const res = await fetch("/api/auth/google-bridge", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(supabaseAccessToken ? { Authorization: `Bearer ${supabaseAccessToken}` } : {}),
      },
      body: JSON.stringify({ access_token: supabaseAccessToken }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(data?.detail ?? "Đăng nhập bằng Google thất bại");
    }
    const lienKet = await layLienKet(data.access_token);
    const user: AuthUser = { ...data.user, ...lienKet };
    setState({ user, accessToken: data.access_token, loading: false });
    return user;
  }, []);

  const register = useCallback(async (payload: RegisterData) => {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(data?.detail ?? "Đăng ký thất bại");
    }
    // Không auto-login sau đăng ký — redirect về trang đăng nhập
    return data.user as AuthUser;
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    setState({ user: null, accessToken: null, loading: false });
  }, []);

  const updateSession = useCallback((accessToken: string, user: AuthUser) => {
    setState((prev) => ({ ...prev, accessToken, user }));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, loginWithGoogle, register, logout, updateSession }),
    [state, login, loginWithGoogle, register, logout, updateSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() phải dùng bên trong <AuthProvider>");
  return ctx;
}
