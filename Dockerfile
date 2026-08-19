# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

# Virtualenv o /opt/venv thay vi `pip install --user` (-> /root/.local):
# container chay bang `appuser`, ma /root co mode 0700 nen appuser KHONG doc
# duoc /root/.local -> moi import se ModuleNotFoundError du PATH da tro dung.
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# Copy venv (doc duoc boi moi user, khong nam duoi /root)
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Khong ghi .pyc va khong buffer stdout/stderr -> log hien ngay trong
# `railway logs` thay vi bi giu trong buffer khi crash.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DRUG_KNOWLEDGE_V2_DIR=/app/data/drug-knowledge-v2

# Security: run as non-root user
RUN useradd -m appuser

# Copy application code
COPY . .

# Runtime V2 data is copied from the promoted Final Canonical artifact. The
# image deliberately excludes Legacy V1, raw snapshots, and review history.
COPY ["data pharmacy/v2/final_canonical/manifest.json", "data pharmacy/v2/final_canonical/drug_product.jsonl", "data pharmacy/v2/final_canonical/drug_id_map.jsonl", "data pharmacy/v2/final_canonical/drug_product_ingredient.jsonl", "data pharmacy/v2/final_canonical/drug_knowledge.jsonl", "/app/data/drug-knowledge-v2/"]
COPY ["data pharmacy/v2/final_canonical/rag/v2_chunks.jsonl", "data pharmacy/v2/final_canonical/rag/v2_embedding_index.jsonl", "/app/data/drug-knowledge-v2/rag/"]

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

# EXPOSE chi la metadata (khong mo port that) - giu 8000 lam gia tri mac dinh
# cho local/docker-compose. Luc chay THAT tren Railway, port do bien PORT
# quyet dinh (Railway inject), xem CMD ben duoi.
EXPOSE 8000

# Doc PORT tu os.environ trong Python thay vi noi chuoi trong shell - tranh
# chuyen quoting long nhau giua HEALTHCHECK shell-form va python -c.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT', '8000') + '/health')" || exit 1

# Dang ["sh", "-c", "exec ..."] chu KHONG phai shell-form `CMD uvicorn ...`:
#   - `sh -c` de ${PORT} duoc expand (exec-form thuan khong expand bien).
#   - `exec` de uvicorn THAY THE sh, giu nguyen PID 1. Neu thieu `exec`, sh
#     lam PID 1 va KHONG forward SIGTERM xuong uvicorn -> lifespan shutdown
#     (stop_escalation_scheduler, backend/main.py) khong bao gio chay khi Railway
#     redeploy/restart, APScheduler job bi bo lai trong jobstore Postgres.
# ${PORT:-8000} giu nguyen hanh vi cu khi chay local/docker-compose (khong co PORT).
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
