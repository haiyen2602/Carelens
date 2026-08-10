# Deploy

Repo này có **2 app độc lập**, mỗi app là **1 Vercel project riêng**:

| App | Thư mục | Vercel project | Framework | URL |
|---|---|---|---|---|
| Backend | `.` (dùng `src/`) | `capymedi` | FastAPI | https://capymedi.vercel.app |
| Frontend | `frontend/` | `capymedi-web` | Next.js | https://capymedi-web.vercel.app |

Hai app nối với nhau qua 2 biến môi trường:

```
frontend  --NEXT_PUBLIC_API_URL-->  backend
backend   --CORS_ORIGINS--------->  frontend
```

Đổi domain một bên thì **phải cập nhật biến ở bên kia rồi redeploy** — env var trên
Vercel chỉ áp dụng cho deployment mới, không tác động lên deployment đang chạy.

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

make preview-api    # backend  -> preview URL
make preview-web    # frontend -> preview URL

make smoke          # chỉ smoke test domain production, không deploy
```

Trên Windows make gọi `cmd.exe` làm shell (không có `sh` trong PATH), các target deploy
đã viết để chạy được ở cả hai shell. Riêng `make clean` dùng `find`/`rm` nên chỉ chạy
được trên POSIX.

Nếu không muốn cài `make`, [scripts/deploy.ps1](../scripts/deploy.ps1) làm việc tương đương:

```powershell
./scripts/deploy.ps1                 # cả api + web -> production, kèm smoke test
./scripts/deploy.ps1 -Target api     # chỉ backend
./scripts/deploy.ps1 -Target web     # chỉ frontend
./scripts/deploy.ps1 -Preview        # ra preview URL thay vì production
```

Hoặc gọi thẳng CLI:

```bash
vercel deploy --prod                 # backend (chạy ở root repo)
cd frontend && vercel deploy --prod  # frontend, hoặc: pnpm deploy
```

## Deploy tự động (GitHub Actions)

[.github/workflows/deploy.yml](../.github/workflows/deploy.yml) chạy khi push lên `main`.
Workflow lọc theo đường dẫn: commit chỉ đụng `frontend/` sẽ **không** redeploy backend.
Có thể chạy tay qua tab Actions → Deploy → Run workflow (chọn `api` / `web` / `both`).

### Secrets cần thêm vào GitHub

Settings → Secrets and variables → Actions:

| Secret | Giá trị |
|---|---|
| `VERCEL_TOKEN` | Tạo ở https://vercel.com/account/tokens |
| `VERCEL_ORG_ID` | `team_51PSrhskGDB2REyCck9oLuIa` |
| `VERCEL_PROJECT_ID_API` | `prj_GQO6lfYFPCF1PKRPFjOF5aCMzR3e` |
| `VERCEL_PROJECT_ID_WEB` | `prj_RXfVKqSegrpCkt6qpSFm9qVZ8Mdj` |

`ORG_ID` / `PROJECT_ID` lấy lại được từ `.vercel/project.json` và
`frontend/.vercel/project.json` (2 file này gitignored, chỉ có trên máy đã `vercel link`).

---

## Environment variables

Env được lưu trên Vercel, **không** đọc từ `.env` khi deploy. Xem bằng `vercel env ls`.

### `capymedi` (backend)

| Biến | Production | Ghi chú |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | Đã set cho cả production/preview/development |
| `CORS_ORIGINS` | `https://capymedi-web.vercel.app,http://localhost:3000` | Danh sách phân tách bằng dấu phẩy, **so khớp chính xác** |
| `APP_ENV` | `production` | |

### `capymedi-web` (frontend)

| Biến | Production | Ghi chú |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://capymedi.vercel.app` | Development trỏ `http://localhost:8000` |

Sửa env:

```bash
vercel env add  <TÊN> production      # nhập giá trị qua stdin
vercel env rm   <TÊN> production
vercel env pull .env.local            # kéo về máy để chạy local
```

---

## Setup cho dev mới

```bash
# backend
vercel link --yes --project capymedi
vercel env pull .env

# frontend
cd frontend
vercel link --yes --project capymedi-web
vercel env pull .env.local
```

---

## Những chỗ dễ vấp

**Một thư mục chỉ link được 1 project.** Trước đây cả `.vercel/` lẫn `frontend/.vercel/`
cùng trỏ vào `capymedi` (project FastAPI), nên deploy từ `frontend/` lại build backend.
Nếu deploy ra nhầm app, kiểm tra `cat .vercel/project.json` xem `projectName` có đúng không.

**CORS lỗi sau khi đổi env.** Env mới chỉ có hiệu lực ở deployment kế tiếp — phải
`make deploy-api` lại. Triệu chứng: preflight `OPTIONS` trả `400` và thiếu header
`Access-Control-Allow-Origin`.

**Preview URL bị CORS chặn.** Preview của frontend có URL ngẫu nhiên
(`capymedi-web-<hash>-...vercel.app`) nên không nằm trong `CORS_ORIGINS`. Test preview
frontend với backend thật thì thêm URL đó vào `CORS_ORIGINS`, hoặc chạy backend local.

**Serverless không có disk ghi được.** `database_url` (SQLite) và `chroma_persist_dir`
trong [src/config.py](../src/config.py) trỏ tới `./data/` — chỉ hoạt động khi chạy local
hoặc Docker. Khi nào bật thật ChromaDB/SQLite thì backend phải chuyển sang host chạy
container (đã có sẵn [Dockerfile](../Dockerfile)) hoặc đổi qua managed service.

**Bundle backend ~45MB**, chủ yếu là `langchain` + `langgraph`. [.vercelignore](../.vercelignore)
đã loại `data pharmacy/`, `docs/`, `frontend/`, `src/vlm_demthuoc/` khỏi upload. Giới hạn
serverless function là 250MB sau giải nén — thêm dependency nặng (torch, opencv) sẽ vượt.

---

## Smoke test

```bash
curl https://capymedi.vercel.app/api/v1/status
# {"status":"ready","agent":"LangGraph Agent v1.0"}

curl -X POST https://capymedi.vercel.app/api/v1/chat \
  -H "Content-Type: application/json" -d '{"message":"xin chao"}'

# CORS — phải thấy Access-Control-Allow-Origin
curl -i -X OPTIONS https://capymedi.vercel.app/api/v1/status \
  -H "Origin: https://capymedi-web.vercel.app" \
  -H "Access-Control-Request-Method: GET"
```

Lưu ý: `https://capymedi.vercel.app/` trả `404` là **đúng** — backend không có route `/`.
Health check nằm ở `/health`, API ở `/api/v1/*`.
