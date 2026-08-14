# Deploy

Repo này có **2 app độc lập**, deploy vào **cùng 1 project Railway** (`VMEC-04`,
environment `production`) nhưng là **2 service riêng**:

| App | Thư mục | Service Railway | Framework | URL |
|---|---|---|---|---|
| Backend | `.` (dùng `backend/`) | `VMEC-04/BE` | FastAPI | https://vmec-04be-production.up.railway.app |
| Frontend | `frontend/` | `VMEC-04/FE` | Next.js 16 | https://vmec-04fe-production.up.railway.app |

Cùng project còn service `VMEC-04/DB` (Postgres + pgvector) mà backend dùng.

Hai app nối với nhau qua 2 biến môi trường:

```
frontend  --NEXT_PUBLIC_API_URL-->  backend
backend   --CORS_ORIGINS--------->  frontend
```

Đổi domain một bên thì **phải cập nhật biến ở bên kia**. Lưu ý bất đối xứng quan trọng:

- `CORS_ORIGINS` là **runtime var** — backend đọc lúc khởi động, nên đổi biến là Railway
  restart container và có hiệu lực ngay, **không cần build lại**.
- `NEXT_PUBLIC_API_URL` là **build-time var** — Next.js nhúng thẳng giá trị vào bundle JS
  lúc `next build`. Đổi biến này thì **phải `railway up` lại**; restart suông vẫn giữ URL
  cũ vì nó đã nằm trong file `.js` của image.

---

## Deploy thủ công

Cần `make`. Trên Windows cài một lần bằng scoop (shim tự vào PATH):

```powershell
scoop install make
```

Rồi chạy từ root repo:

```bash
make deploy         # cả hai -> production, kèm smoke test
make deploy-api     # backend  -> production
make deploy-web     # frontend -> production

make smoke          # chỉ smoke test domain production, không deploy
```

Nếu không muốn cài `make`, [scripts/deploy.ps1](../scripts/deploy.ps1) làm việc tương đương:

```powershell
./scripts/deploy.ps1                 # cả api + web -> production, kèm smoke test
./scripts/deploy.ps1 -Target api     # chỉ backend
./scripts/deploy.ps1 -Target web     # chỉ frontend
```

Hoặc gọi thẳng CLI:

```bash
railway up -c                        # backend (chạy ở root repo)
cd frontend && railway up -c         # frontend, hoặc: pnpm deploy
```

`railway up` **upload thẳng thư mục hiện tại** rồi build trên Railway (không đi qua git),
nên deploy được cả khi đang có thay đổi chưa commit. Cờ `-c` chỉ stream build log rồi
thoát — thiếu nó thì CLI bám vào log runtime và treo terminal.

## Deploy tự động (GitHub Actions)

[.github/workflows/deploy.yml](../.github/workflows/deploy.yml) chạy khi push lên `main`.
Workflow lọc theo đường dẫn: commit chỉ đụng `frontend/` sẽ **không** redeploy backend.
Chạy tay được qua tab Actions → Deploy → Run workflow (chọn `api` / `web` / `both`).

### Secrets cần thêm vào GitHub

Settings → Secrets and variables → Actions:

| Secret | Giá trị |
|---|---|
| `RAILWAY_TOKEN` | Tạo ở https://railway.com/account/tokens (project token của `VMEC-04` là đủ) |

Chỉ cần **1 secret** — service và environment truyền qua cờ `--service` / `--environment`
nên runner không cần `railway link`.

---

## Environment variables

Env lưu trên Railway, **không** đọc từ `.env` khi deploy. Xem bằng `railway variables`.

### `VMEC-04/BE` (backend)

| Biến | Ghi chú |
|---|---|
| `OPENAI_API_KEY` | |
| `INTERNAL_AUTH_SECRET` | Bắt buộc — app **từ chối khởi động** nếu còn giá trị sentinel trong source |
| `DATABASE_URL` | Reference var trỏ sang service `VMEC-04/DB` |
| `CORS_ORIGINS` | Chỉ còn `https://vmec-04fe-production.up.railway.app`. Phân tách bằng dấu phẩy, **so khớp chính xác** |
| `APP_ENV` / `APP_HOST` / `LOG_LEVEL` / `EMBEDDING_MODEL` | Cấu hình app |

Hai origin `*.vercel.app` (backend cũ project `capymedi` và frontend cũ `capymedi-web`) đã được
**xoá hẳn** khỏi `CORS_ORIGINS` ngày 2026-08-13 — dự án không còn deploy trên Vercel. Frontend
production giờ là `https://vmec-04fe-production.up.railway.app` (service `VMEC-04/FE`) và đó là
origin duy nhất được phép. Biến đặt kèm `--skip-deploys` nên chỉ có hiệu lực sau lần
restart/redeploy BE kế tiếp (`settings.cors_origins` đọc một lần lúc khởi động,
`backend/main.py:58`).

### `VMEC-04/FE` (frontend)

| Biến | Giá trị | Ghi chú |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://vmec-04be-production.up.railway.app` | **Build-time** — xem ghi chú ở đầu file |
| `NEXT_TELEMETRY_DISABLED` | `1` | |

Sửa env:

```bash
railway variables                                  # liệt kê service đang link
railway variables --set "TÊN=giá trị"              # thêm/sửa (tự trigger redeploy)
railway variables --service "VMEC-04/FE"           # xem service khác
```

---

## Setup cho dev mới

Mỗi thư mục link tới **1 service riêng** — link ở root **không** tự áp cho `frontend/`:

```bash
railway login

# backend
railway link --project VMEC-04 --environment production --service "VMEC-04/BE"

# frontend
cd frontend
railway link --project VMEC-04 --environment production --service "VMEC-04/FE"
```

Kéo env về máy để chạy local:

```bash
railway variables --kv > .env             # ở root, cho backend
cd frontend && cp .env.example .env.local # frontend chỉ cần NEXT_PUBLIC_API_URL
```

---

## Những chỗ dễ vấp

**`railway up` ở `frontend/` mà chưa `railway link` thư mục đó** thì CLI đi ngược lên tìm
link của thư mục cha, rồi upload **cả repo** và build `Dockerfile` của backend vào service
frontend. Triệu chứng: build log của service FE chạy `pip install -r requirements.txt`.
Fix: `railway link` riêng trong `frontend/` (xem mục trên).

**Target port của domain phải khớp port app thật sự listen.** Railway inject `PORT=8080`,
Next.js standalone `server.js` đọc `PORT` nên listen 8080 — dù Dockerfile có `EXPOSE 3000`.
Domain trỏ sai port trả `502 Application failed to respond` mặc dù container log `✓ Ready`.
Kiểm tra ở dashboard → service → Settings → Networking.

**`HOSTNAME=0.0.0.0` là bắt buộc cho frontend.** `server.js` của Next.js standalone mặc
định bind `localhost`, Railway không route được traffic từ ngoài vào → healthcheck fail.
Đã set trong [frontend/Dockerfile](../frontend/Dockerfile).

**Đổi `NEXT_PUBLIC_API_URL` mà không build lại** thì frontend vẫn gọi URL cũ. Với Dockerfile
build, biến chỉ vào được build qua `ARG` (Docker cách ly build khỏi env của host) — và `ARG`
phải khai báo **trong đúng stage** dùng nó, không xuyên stage.

**Frontend có 2 lockfile** (`package-lock.json` + `pnpm-lock.yaml`). Dockerfile chỉ copy
`pnpm-lock.yaml` để build luôn dùng pnpm thay vì tuỳ builder đoán. Thêm dependency thì nhớ
cập nhật lockfile bằng `pnpm`, không phải `npm`.

**Backend từ chối khởi động nếu thiếu `INTERNAL_AUTH_SECRET` thật.** Sentinel
`unset-temp-auth-gate-CHANGE-ME-for-any-shared-env` nằm sẵn trong source nên bị chặn.
Triệu chứng: deploy FAILED, log có `ValidationError ... internal_auth_secret`.

**`preDeployCommand` chạy `alembic upgrade head`** ([railway.json](../railway.json)) trước
mỗi lần deploy backend. Volume **không** được mount lúc build và lúc pre-deploy, chỉ lúc
container chạy.

---

## Smoke test

```bash
curl https://vmec-04be-production.up.railway.app/api/v1/status
# {"status":"ready","agent":"LangGraph Agent v1.0"}

curl -X POST https://vmec-04be-production.up.railway.app/api/v1/chat \
  -H "Content-Type: application/json" -d '{"message":"xin chao"}'

# CORS — phải thấy Access-Control-Allow-Origin
curl -i -X OPTIONS https://vmec-04be-production.up.railway.app/api/v1/status \
  -H "Origin: https://vmec-04fe-production.up.railway.app" \
  -H "Access-Control-Request-Method: GET"

curl -o /dev/null -w "%{http_code}\n" https://vmec-04fe-production.up.railway.app/
# 200
```

Lưu ý: `https://vmec-04be-production.up.railway.app/` trả `404` là **đúng** — backend không
có route `/`. Health check ở `/health`, API ở `/api/v1/*`.

Xem log và trạng thái:

```bash
railway logs                    # log runtime của service đang link
railway logs --build            # log build
railway status                  # trạng thái toàn project
```
