# Kế hoạch chuyển hạ tầng — DB + backend + frontend ra khỏi local/Vercel serverless

> **Quyết định 2026-08-11, cập nhật 2026-08-12, 2026-08-13** (Nguyễn Minh Đạt, PM) — trạng thái: **ĐÃ HOÀN TẤT**
> (chỉ còn 1 việc dọn dẹp không chặn hoạt động, xem "Việc còn lại").
> File này là nguồn sự thật DUY NHẤT về hạ tầng đang chuyển đổi — nếu thấy mô tả ở đây khác với
> những gì đang chạy thật, tin vào cái đang chạy thật, sửa lại file này, không phải ngược lại. Hạ
> tầng đang chạy thật xem thêm `docs/DEPLOY.md`.

## Vấn đề đã xác nhận (không phải suy đoán)

1. Database hiện chạy **local** (docker-compose, máy dev) — mỗi máy 1 dữ liệu khác nhau, backend
   deploy không có DB nào để trỏ tới.
2. Backend cũ (`capymedi` trên Vercel) **đang crash 500** (`FUNCTION_INVOCATION_FAILED`, xác nhận
   qua `curl` ngày 2026-08-11) — do thiếu `DATABASE_URL` thật + `INTERNAL_AUTH_SECRET` (validator
   fail-closed, `src/config.py`, mục 10 #10 của `chatbot-rag-design.md`).
3. **Lý do sâu hơn:** backend dùng `AsyncIOScheduler` chạy TRONG process (mục 13 — nhắc lại
   escalation) — Vercel serverless không có tiến trình sống liên tục giữa các request, không tương
   thích về bản chất, không phải lỗi code.

## Kiến trúc đích — CẬP NHẬT 2026-08-12: cả 3 tầng đều trên Railway, không dùng Vercel nữa

```
Railway project "VMEC-04" (environment production), 3 service cùng project — project từng có tên
"gleaming-growth" lúc mới tạo, đã đổi tên thành "VMEC-04" (xác nhận 2026-08-12, sau khi cả
DEPLOY.md/Makefile/CI đã viết xong dựa trên tên cũ — đã sửa lại đồng bộ, xem "Việc còn lại"):

  VMEC-04/FE  (Next.js frontend)   ── https://vmec-04fe-production.up.railway.app
  VMEC-04/BE  (FastAPI backend, code ở backend/, KHÔNG còn ở src/) ── https://vmec-04be-production.up.railway.app
  VMEC-04/DB  (service `Postgres`, pg 18.4 + pgvector, tự deploy Docker, có volume db-volume)
```

**Phát hiện 2026-08-12 (review lại trước khi sửa DEPLOY.md):** `src/` đã được **đổi tên hẳn** thành
`backend/` (không phải bản sao) — `src/` hiện rỗng hoàn toàn (chỉ còn rác `__pycache__`).
`railway.json` (mới, `preDeployCommand: alembic upgrade head`), `Makefile`, `scripts/deploy.ps1`
đều đã cập nhật sang `railway up`/`backend/`. Việc này KHÔNG làm trong phiên hiện tại — xác nhận
qua diff thư mục + `git log` (tác giả trùng git identity của Nguyễn Minh Đạt), nhiều khả năng làm
qua công cụ/phiên khác song song. Mọi tham chiếu `src/...` ở các mục cũ trong file này (vd mục
"Vấn đề đã xác nhận" phía trên nhắc `src/config.py`) mô tả đúng lúc phát hiện (trước khi đổi tên),
giữ nguyên để lịch sử, đường dẫn thật bây giờ là `backend/...`.

**Đổi 2 lần so với kế hoạch gốc:** ban đầu định Supabase cho DB (giữ Vercel cho frontend) → đổi
sang Postgres trên Railway (cùng platform với backend, 2026-08-12 lần 1) → xác nhận thêm frontend
**cũng** đã chuyển hẳn sang Railway (`VMEC-04/FE`), Vercel (`capymedi-web`) không còn là bản
production nữa (2026-08-12 lần 2, xác nhận trực tiếp với Nguyễn Minh Đạt).

Lợi thế: cả 3 service cùng 1 Railway project → dùng được mạng nội bộ Railway giữa BE↔DB, không cần
đồng bộ env qua nhiều platform khác nhau (đỡ đúng đúng loại lỗi từng gặp — quên đồng bộ
`INTERNAL_AUTH_SECRET` giữa 2 platform).

## Trạng thái từng phần

| Phần | Trạng thái |
|---|---|
| Dump/restore data local (`drug_chunks`) sang Postgres trên Railway | ✅ Đã làm |
| Xác nhận extension `vector`/`pg_trgm`/`unaccent` + số dòng `drug_chunks` | ✅ **Đã xác nhận 2026-08-12** qua `psql` thật: cả 4 extension (`plpgsql`, `vector`, `pg_trgm`, `unaccent`) có đủ; `drug_chunks = 14,447` — khớp CHÍNH XÁC số dry-run ước tính trước đó (`scripts/embed_and_insert.py --dry-run`) |
| Deploy backend (`VMEC-04/BE`) lên Railway | ✅ Đã làm — service Online |
| Deploy frontend (`VMEC-04/FE`) lên Railway | ✅ Đã làm — service Online, **thay thế hẳn Vercel `capymedi-web`** |
| Bật TCP Proxy public cho `VMEC-04/DB` (dùng để kiểm tra tay qua `psql`) | ✅ Đã làm — `altaria.proxy.rlwy.net:23551` → `:5432` |
| Set env cho `VMEC-04/BE`: `DATABASE_URL`, `OPENAI_API_KEY`, `INTERNAL_AUTH_SECRET`, `CORS_ORIGINS`, `APP_ENV` (+ `APP_HOST`/`EMBEDDING_MODEL`/`LOG_LEVEL`) | ✅ Đã làm — 8 biến xác nhận có mặt trong Variables |
| Set env cho `VMEC-04/FE`: `NEXT_PUBLIC_API_URL`, `INTERNAL_AUTH_SECRET` (khớp BE) | ✅ Đã làm |
| Redeploy BE + FE sau khi set env | ✅ Đã làm — cả 2 Online |
| Smoke test end-to-end qua chính domain Railway FE | ✅ **Đã xác nhận 2026-08-12 — chatbot chat được bình thường qua domain FE thật**, không phải qua Vercel |
| Xoá origin Vercel cũ (`capymedi`) khỏi `CORS_ORIGINS` của `VMEC-04/BE` | ✅ Đã làm — 2026-08-13 |
| Dừng/xoá hẳn project Vercel `capymedi` (backend cũ, đang crash) và `capymedi-web` (frontend cũ, không còn dùng) | ✅ **Đã xoá hẳn cả 2 project — 2026-08-13** |
| Cập nhật `docs/DEPLOY.md` theo kiến trúc Railway-only | ✅ **Đã xong** — phát hiện 2026-08-12, viết chi tiết hơn bản định làm trong phiên này (tên project `gleaming-growth`, `railway.json`, các gotcha PORT/HOSTNAME đã fix) — không sửa thêm, tránh ghi đè mất thông tin thật |
| Đổi tên `src/` → `backend/`, thêm `railway.json`, cập nhật `Makefile`/`scripts/deploy.ps1` sang `railway up` | ✅ Đã xong (phát hiện 2026-08-12, không rõ làm lúc nào/qua công cụ gì) |
| Xoá rác thư mục `src/` rỗng (chỉ còn `__pycache__`) | ⏳ Cần Nguyễn Minh Đạt xác nhận đây là chủ đích trước khi xoá hẳn |

## Việc còn lại

1. Xác nhận `src/` rỗng là chủ đích (đã chuyển hẳn sang `backend/`) rồi dọn nốt thư mục rỗng —
   việc dọn dẹp duy nhất còn lại, không chặn hoạt động (Vercel `capymedi`/`capymedi-web` đã xoá hẳn,
   xem bảng trạng thái).
