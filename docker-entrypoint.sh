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

# Doc thang tu Settings thay vi hardcode duong dan o day - doi
# PHOTO_STORAGE_DIR sau nay khong lam entrypoint tro sai cho.
# `|| echo ...` co chu dich: get_settings() la fail-closed (thieu JWT_SECRET/
# INTERNAL_AUTH_SECRET la raise). Neu no hong o day thi van chinh quyen thu
# muc mac dinh roi de APP tu bao loi that - dung de entrypoint chet truoc,
# che mat thong bao loi cau hinh von ro rang hon nhieu.
PHOTO_DIR=$(python -c 'from backend.config import get_settings; print(get_settings().photo_storage_dir)' 2>/dev/null \
    || echo './data/photo_verifications')

mkdir -p "$PHOTO_DIR"
chown -R appuser:appuser "$PHOTO_DIR"

# `exec` de gosu THAY THE shell nay, va uvicorn (qua CMD) giu nguyen PID 1 -
# neu khong, SIGTERM luc Railway redeploy khong xuong toi uvicorn, lifespan
# shutdown (stop_escalation_scheduler) khong chay, APScheduler job ket lai
# trong jobstore Postgres. Cung ly do da ghi trong CMD cua Dockerfile.
exec gosu appuser "$@"
