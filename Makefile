.PHONY: run test lint format typecheck check clean deploy-api deploy-web deploy preview-api preview-web smoke smoke-api smoke-web

# /dev/null trên POSIX, NUL trên Windows (make gọi cmd.exe khi không có sh trong PATH)
NULLDEV := /dev/null
ifeq ($(OS),Windows_NT)
NULLDEV := NUL
endif

run:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

lint:
	ruff check backend/ tests/

format:
	ruff format backend/ tests/

typecheck:
	mypy backend/

check: lint format test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +

# --- Deploy (Railway) --- see docs/DEPLOY.md
# Project `VMEC-04`, environment `production`:
#   api = FastAPI, service VMEC-04/BE, root .
#   web = Next.js,  service VMEC-04/FE, root frontend/
#
# `railway up` upload thẳng thư mục hiện tại rồi build trên Railway (không qua
# git), nên deploy được cả khi đang có thay đổi chưa commit.
# -c: chỉ stream build log rồi thoát, tránh treo terminal ở log runtime.

deploy-api:
	railway up -c --service VMEC-04/BE

deploy-web:
	cd frontend && railway up -c --service VMEC-04/FE

deploy: deploy-api deploy-web smoke

# Railway không có "preview deploy" như Vercel. Cách tương đương là environment
# riêng: `railway environment new preview` rồi deploy vào đó với -e preview.
preview-api:
	railway up -c --service VMEC-04/BE -e preview

preview-web:
	cd frontend && railway up -c --service VMEC-04/FE -e preview

smoke: smoke-api smoke-web

smoke-api:
	curl -fsS --max-time 30 -w "\napi -> HTTP %{http_code}\n" https://vmec-04be-production.up.railway.app/api/v1/status

smoke-web:
	curl -fsS --max-time 30 -o $(NULLDEV) -w "web -> HTTP %{http_code}\n" https://vmec-04fe-production.up.railway.app/
