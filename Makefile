.PHONY: run test lint format typecheck check clean deploy-api deploy-web deploy preview-api preview-web smoke smoke-api smoke-web

# /dev/null trên POSIX, NUL trên Windows (make gọi cmd.exe khi không có sh trong PATH)
NULLDEV := /dev/null
ifeq ($(OS),Windows_NT)
NULLDEV := NUL
endif

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

check: lint format test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +

# --- Deploy (Vercel) --- see docs/DEPLOY.md
# api = FastAPI, project `capymedi`, root .
# web = Next.js, project `capymedi-web`, root frontend/

deploy-api:
	vercel deploy --prod

deploy-web:
	cd frontend && vercel deploy --prod

deploy: deploy-api deploy-web smoke

preview-api:
	vercel deploy

preview-web:
	cd frontend && vercel deploy

# Smoke test domain production. Preview deploy ra URL ngẫu nhiên nên không test được ở đây.
smoke: smoke-api smoke-web

smoke-api:
	curl -fsS --max-time 30 -w "\napi -> HTTP %{http_code}\n" https://capymedi.vercel.app/api/v1/status

smoke-web:
	curl -fsS --max-time 30 -o $(NULLDEV) -w "web -> HTTP %{http_code}\n" https://capymedi-web.vercel.app/
