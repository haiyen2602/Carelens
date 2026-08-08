# Seamless Patient Flow

Prototype bấm được (chưa kết nối core) cho 3 luồng: bác sĩ (desktop), bệnh nhân và người thân (mobile web).

Stack: Next.js (App Router) + React 19 + Tailwind v4 + shadcn/ui + TanStack Query.

## Development

```sh
npm i
cp .env.example .env.local   # chỉnh NEXT_PUBLIC_API_URL nếu backend không chạy ở localhost:8000
npm run dev
```

Mở http://localhost:3000. Trang đăng nhập rẽ vai bác sĩ/bệnh nhân/người thân (`/`, `/doctor`, `/patient`, `/family`).

## Scripts

- `npm run dev` — dev server (Turbopack)
- `npm run build` — production build
- `npm run start` — chạy bản build
- `npm run lint` — eslint
- `npm run format` — prettier --write
