import { betterAuth } from "better-auth";
import { Pool } from "pg";

// "Login with Google" (Better Auth) - CHI la moi gioi OAuth, KHONG phai nguon
// su that ve danh tinh.
//
// Danh tinh that cua he thong van la bang `account` cua backend + JWT
// (Authorization: Bearer <JWT>, payload sub/role/patient_id) - 40 route backend
// deu doc role tu do. Better Auth o day chi lam dung 1 viec: noi chuyen voi
// Google va xac minh ket qua. Ngay sau khi no xong, Route Handler
// `app/api/auth/google-bridge/route.ts` doi danh tinh do sang JWT that qua
// POST /api/v1/auth/oauth/google roi HUY phien Better Auth - de trong he thong
// chi ton tai DUY NHAT 1 khai niem phien dang nhap (refresh_token httpOnly
// cookie + access_token trong memory, xem lib/auth.tsx).
//
// basePath `/api/better-auth` (KHONG phai `/api/auth` mac dinh): thu muc
// `app/api/auth/` DA CO cac Route Handler rieng cua du an (login, register,
// refresh, logout, google-bridge). Next.js uu tien route tinh hon catch-all
// nen ve ly thuyet chung song song duoc, nhung dat rieng basePath thi khong
// phai dua vao thu tu do - va doc URL la biet ngay dau la endpoint cua du an,
// dau la cua Better Auth.
//
// Chay TREN SERVER (Route Handler): `pg` va secret khong bao gio vao bundle
// trinh duyet. Phia client dung lib/better-auth-client.ts.

const DATABASE_URL = process.env.DATABASE_URL ?? "";
const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID ?? "";
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET ?? "";

/** Thieu 1 trong 4 bien -> nut "Đăng nhập bằng Google" bi an va endpoint tra
 * loi ro rang, thay vi de Better Auth khoi tao voi clientId rong roi that bai
 * giua luong OAuth bang mot trang loi cua Google (rat kho doan nguyen nhan). */
export const googleAuthConfigured = Boolean(
  DATABASE_URL && GOOGLE_CLIENT_ID && GOOGLE_CLIENT_SECRET && process.env.BETTER_AUTH_SECRET,
);

// `new Pool` o module scope: Next.js giu module song giua cac request nen day
// la 1 pool dung chung, khong phai 1 ket noi moi cho tung request. Pool nho -
// pool that (cho toan bo du lieu benh nhan) nam o backend FastAPI; pool nay chi
// phuc vu 4 bang ba_* trong vai giay cua luong OAuth.
const pool = DATABASE_URL
  ? new Pool({
      connectionString: DATABASE_URL,
      max: 3,
      // Railway Postgres qua public proxy yeu cau TLS; qua private network thi
      // khong. `rejectUnauthorized: false` chi ap dung khi URL co sslmode.
      ssl: DATABASE_URL.includes("sslmode=require") ? { rejectUnauthorized: false } : undefined,
    })
  : undefined;

export const auth = betterAuth({
  appName: "CapyMedi",
  basePath: "/api/better-auth",
  // baseURL/secret KHONG dat o day khi da co BETTER_AUTH_URL/BETTER_AUTH_SECRET
  // trong env (theo huong dan cua Better Auth). BETTER_AUTH_URL BAT BUOC tren
  // production: thieu no, callback URL roi ve localhost va Google bao loi
  // redirect_uri_mismatch.
  database: pool,
  // Better Auth doi hoi schema rieng (user/session/account/verification). Bang
  // `account` cua du an DA TON TAI voi hinh dang hoan toan khac (role,
  // patient_id, password_hash - migration 0012), nen 4 bang cua Better Auth
  // duoc doi ten sang tien to `ba_` (migration 0025). Day la `modelName` -
  // Better Auth khong biet ten bang that nao khac ngoai cai duoc khai bao o day.
  user: { modelName: "ba_user" },
  // Phien Better Auth chi song vai giay (tu callback Google -> google-bridge
  // huy no). `expiresIn` ngan de mot phien "mo coi" (nguoi dung dong tab dung
  // giua luong) khong nam lai trong DB ca tuan nhu mac dinh 7 ngay.
  session: { modelName: "ba_session", expiresIn: 60 * 10 },
  account: { modelName: "ba_account" },
  verification: { modelName: "ba_verification" },
  // Dang ky/dang nhap bang mat khau VAN do backend FastAPI xu ly
  // (POST /api/v1/auth/login, bcrypt trong bang `account`) - tat o day de
  // khong tao ra duong dang nhap thu hai bang mat khau, di qua toan bo
  // kiem tra `status != "active"` va thu hoi token cua backend.
  emailAndPassword: { enabled: false },
  socialProviders: {
    google: {
      clientId: GOOGLE_CLIENT_ID,
      clientSecret: GOOGLE_CLIENT_SECRET,
      // Bat nguoi dung chon tai khoan moi lan - may dung chung (dien thoai cua
      // nguoi than, may tinh phong kham) khong nen tu dong dang nhap lai vao
      // tai khoan Google cuoi cung da dung.
      prompt: "select_account",
    },
  },
  // Phien Better Auth chi song vai giay (tu callback Google -> google-bridge
  // huy no). Dat han ngan de mot phien "mo coi" (nguoi dung dong tab dung
  // giua luong) khong nam lai trong DB ca tuan nhu mac dinh 7 ngay.
  // trustedOrigins: chan CSRF. Chi can khi FE va BETTER_AUTH_URL khac origin;
  // giu mac dinh (chinh baseURL) la du cho ca local va Railway.
});

export type BetterAuthSession = Awaited<ReturnType<typeof auth.api.getSession>>;
