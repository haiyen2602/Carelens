# Next.js 16 (App Router) tren Railway.
#
# Node 24 de khop voi may dev (node v24.16.0) - package.json khong co field
# `engines` nen khong co rang buoc nao khac de dua theo.

# ---- Stage 1: Dependencies ----
FROM node:24-slim AS deps

WORKDIR /app

# Pin pnpm dung ban tren may dev (11.9.0) thay vi `corepack prepare pnpm@11`:
# package.json KHONG co field `packageManager`, nen corepack se bao loi thay vi
# tu chon version.
RUN npm install --global pnpm@11.9.0

# Repo co CA package-lock.json LAN pnpm-lock.yaml. Chi copy pnpm-lock.yaml vao
# day -> build luon dung pnpm, khong bao gio "tuy builder doan".
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# ---- Stage 2: Build ----
FROM node:24-slim AS builder

WORKDIR /app

RUN npm install --global pnpm@11.9.0

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* duoc Next.js NHUNG THANG vao bundle JS luc build, khong phai doc
# luc chay. Docker cach ly build khoi moi truong host, nen bien cua Railway chi
# vao duoc build qua `ARG` (khai bao trong CHINH stage nay - ARG khong xuyen
# stage). Thieu dong nay thi API_BASE trong src/lib/api.ts se roi ve fallback
# http://localhost:8000 va frontend goi vao chinh may nguoi dung.
#
# Doi gia tri bien nay => PHAI build lai; redeploy anh cu van giu URL cu.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Tat telemetry: build tren CI khong can gui thong ke ve Vercel.
ENV NEXT_TELEMETRY_DISABLED=1

RUN pnpm build

# ---- Stage 3: Production ----
FROM node:24-slim AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# Security: run as non-root user
RUN useradd -m appuser

# `output: "standalone"` (next.config.ts) goi san server.js + dung node_modules
# toi thieu vao .next/standalone -> khong can copy toan bo node_modules.
# static/ va public/ nam NGOAI goi standalone nen phai copy tay.
COPY --from=builder --chown=appuser:appuser /app/.next/standalone ./
COPY --from=builder --chown=appuser:appuser /app/.next/static ./.next/static
COPY --from=builder --chown=appuser:appuser /app/public ./public

USER appuser

# EXPOSE chi la metadata (khong mo port that) - 3000 la mac dinh cho local.
# Luc chay that tren Railway, PORT do Railway inject quyet dinh.
EXPOSE 3000

# HOSTNAME=0.0.0.0 la BAT BUOC: server.js cua standalone mac dinh bind
# localhost, nhu vay Railway khong route duoc traffic tu ngoai vao -> healthcheck
# fail va deploy bi danh la crashed.
ENV HOSTNAME=0.0.0.0

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD node -e "require('http').get('http://127.0.0.1:' + (process.env.PORT || 3000) + '/', r => process.exit(r.statusCode < 400 ? 0 : 1)).on('error', () => process.exit(1))"

# Dang ["sh", "-c", "exec ..."] giong Dockerfile backend:
#   - `sh -c` de ${PORT} duoc expand (exec-form thuan khong expand bien).
#   - `exec` de node THAY THE sh, giu PID 1 -> nhan duoc SIGTERM khi Railway
#     redeploy, thoat gon thay vi bi kill sau timeout.
CMD ["sh", "-c", "exec node server.js"]
