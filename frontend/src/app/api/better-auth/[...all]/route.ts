import { toNextJsHandler } from "better-auth/next-js";

import { auth } from "@/lib/better-auth";

// Catch-all cho Better Auth (basePath /api/better-auth, xem lib/better-auth.ts).
// Duong nay phuc vu dung 2 buoc cua luong OAuth:
//   GET/POST /api/better-auth/sign-in/social  - bat dau, chuyen sang Google
//   GET      /api/better-auth/callback/google - Google tra ve, xac minh
// URI thu hai la gia tri PHAI dang ky trong Google Cloud Console
// (Authorized redirect URIs) - xem frontend/.env.example.
//
// KHONG dat o `app/api/auth/[...all]` (mac dinh cua thu vien): thu muc do da co
// login/register/refresh/logout/google-bridge cua du an.
export const { GET, POST } = toNextJsHandler(auth);
