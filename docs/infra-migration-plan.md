# Kế hoạch chuyển hạ tầng — DB + backend ra khỏi local/Vercel serverless

> **Quyết định 2026-08-11** (Nguyễn Minh Đạt, PM) — trạng thái: **ĐANG THỰC HIỆN, chưa xong**.
> File này là nguồn sự thật DUY NHẤT về hạ tầng đang chuyển đổi — nếu thấy mô tả ở đây khác với
> những gì đang chạy thật, tin vào cái đang chạy thật, sửa lại file này, không phải ngược lại.

## Vấn đề đã xác nhận (không phải suy đoán)

1. Database hiện chạy **local** (docker-compose, máy dev) — mỗi máy 1 dữ liệu khác nhau, backend
   deploy không có DB nào để trỏ tới.
2. Backend (`capymedi` trên Vercel) **đang crash 500** (`FUNCTION_INVOCATION_FAILED`, xác nhận qua
   `curl https://capymedi.vercel.app/api/v1/status` ngày 2026-08-11) — do thiếu `DATABASE_URL` thật
   và `INTERNAL_AUTH_SECRET` (validator fail-closed, `src/config.py`, mục 10 #10 của
   `chatbot-rag-design.md`).
3. **Lý do sâu hơn, không chỉ thiếu env var:** backend dùng `AsyncIOScheduler` chạy TRONG process
   (`src/services/escalation_scheduler.py`, khởi động ở `lifespan` trong `src/main.py`) để nhắc lại
   escalation (mục 13 thiết kế) — Vercel serverless không có tiến trình sống liên tục giữa các
   request, cơ chế này về bản chất không tương thích, không phải lỗi code.

## Kiến trúc đích đã chốt

```
Frontend (Next.js)  ── Vercel (project capymedi-web) ── GIỮ NGUYÊN, không đổi gì
Backend (FastAPI+LangGraph) ── Railway (dùng Dockerfile có sẵn, KHÔNG sửa code)
Database (Postgres+pgvector) ── Supabase
```

Lý do chọn Railway thay vì viết lại scheduler thành Vercel Cron: Dockerfile đã chạy đúng sẵn,
Railway build thẳng từ đó — không cần sửa code, `AsyncIOScheduler` chạy đúng ngay.

## Trạng thái từng phần

| Phần | Trạng thái |
|---|---|
| Tạo project Supabase | ⏳ Đang làm (Nguyễn Minh Đạt) |
| Chạy `alembic upgrade head` trỏ Supabase | Chưa làm — chờ connection string |
| Dump/restore data từ máy dev đã có sẵn data sang Supabase | Chưa làm |
| Cập nhật `DATABASE_URL` ở `.env` mọi máy dev | Chưa làm |
| Deploy backend lên Railway (Dockerfile có sẵn) | Chưa làm — chờ `DATABASE_URL` Supabase |
| Set env trên Railway (`DATABASE_URL`, `OPENAI_API_KEY`, `INTERNAL_AUTH_SECRET`, `CORS_ORIGINS`) | Chưa làm |
| Đổi `NEXT_PUBLIC_API_URL` trên Vercel frontend → domain Railway | Chưa làm |
| Bỏ project `capymedi` (backend cũ trên Vercel) | Chưa làm |
| Cập nhật `docs/DEPLOY.md` theo kiến trúc mới | Chưa làm — làm sau khi Railway chạy thật, tránh mô tả cái chưa tồn tại |

## Việc tiếp theo, đúng thứ tự (không nhảy bước)

1. Nguyễn Minh Đạt tạo project Supabase, lấy connection string (session pooler + transaction pooler).
2. Chạy migration + dump/restore data từ máy dev đã có sẵn (không embed lại — tốn phí OpenAI không
   cần thiết).
3. Deploy backend lên Railway từ Dockerfile hiện có.
4. Trỏ frontend sang domain Railway mới, redeploy frontend.
5. Smoke test lại toàn bộ (`/health`, `/api/v1/status`, `/api/v1/chat`) trên domain Railway.
6. Viết lại `docs/DEPLOY.md` theo đúng kiến trúc mới, xoá hướng dẫn deploy backend lên Vercel cũ.
