#!/bin/sh
# Chinh quyen thu muc anh xac nhan lieu RUNTIME roi ha quyen xuong appuser.
#
# Vi sao can (bug that, production 2026-08-22): Dockerfile chay
# `chown -R appuser:appuser /app` LUC BUILD, nhung Railway mount Volume vao
# /app/data/photo_verifications LUC CONTAINER KHOI DONG - volume rong do
# thuoc root, phu de len dung thu muc vua duoc chown. Ket qua: appuser mat
# quyen ghi, moi lan benh nhan gui anh deu 500:
#   PermissionError: [Errno 13] Permission denied:
#     'data/photo_verifications/<dose_id>_<uuid>.jpg'
#   (backend/api/photo_routes.py, buoc Path(duong_dan).write_bytes)
# Chi lo tren Railway, KHONG lo khi chay uvicorn truc tiep tren may dev
# (khong co container, khong co volume mount de len).
#
# Chay o day la dung thoi diem: volume DA mount xong nhung app CHUA khoi
# dong. Sau khi chinh quyen thi `gosu` doi sang appuser ngay - KHONG chay
# app bang root (app nhan anh nguoi dung tai len, chay root la ha cap bao
# mat that su cho dung loai input rui ro nhat).
set -e

# Doc THANG bien moi truong thay vi goi python đọc Settings (SUA sau review
# PR #79): trong container, Settings CHI lay tu bien moi truong - `.env` nam
# trong .dockerignore nen khong bao gio vao image - va Settings khong dat
# env_prefix, nen `photo_storage_dir` chinh la $PHOTO_STORAGE_DIR. Hai cach
# cho ket qua y het, nhung cach nay khong the that bai: goi python o day
# keo theo ca validator fail-closed cua Settings (thieu JWT_SECRET/
# INTERNAL_AUTH_SECRET la raise), tuc them 1 duong hong cho 1 viec chi can
# doc 1 chuoi.
#
# Gia tri mac dinh phai KHOP `photo_storage_dir` trong backend/config.py.
PHOTO_DIR="${PHOTO_STORAGE_DIR:-./data/photo_verifications}"

# KHONG de `set -e` giet container neu 2 lenh nay hong (vd volume gan
# read-only): hong chowned thi chi rieng chuc nang gui anh loi, con lai van
# chay duoc - crash-loop ca backend vi the la phan ung qua tay. In canh bao
# ro rang de con truy duoc trong `railway logs`.
mkdir -p "$PHOTO_DIR" 2>/dev/null \
    || echo "[entrypoint] CANH BAO: khong tao duoc thu muc anh $PHOTO_DIR"
chown -R appuser:appuser "$PHOTO_DIR" 2>/dev/null \
    || echo "[entrypoint] CANH BAO: khong chown duoc $PHOTO_DIR - gui anh xac nhan lieu co the loi 500"

# `exec` de gosu THAY THE shell nay, va uvicorn (qua CMD) giu nguyen PID 1 -
# neu khong, SIGTERM luc Railway redeploy khong xuong toi uvicorn, lifespan
# shutdown (stop_escalation_scheduler) khong chay, APScheduler job ket lai
# trong jobstore Postgres. Cung ly do da ghi trong CMD cua Dockerfile.
exec gosu appuser "$@"
