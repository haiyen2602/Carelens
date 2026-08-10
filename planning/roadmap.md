# Roadmap 5 tuần — VMEC-04

> **Owner:** PM (Nguyễn Hải Yến) · **Cập nhật khi:** đổi mốc, đổi phạm vi tuần
> Bức tranh toàn cảnh 5 tuần. Chi tiết từng sprint: [`./sprints/`](./sprints/). Ưu tiên feature: [`./backlog.md`](./backlog.md).

**Thời gian dự án:** 2026-07-25 → ~2026-08-29 (5 tuần)
**Team:** P-067 (G14 - T067), 4 người kiêm nhiệm — xem [`../TEAM.md`](../TEAM.md)

## Tổng quan

| Sprint | Tuần | Thời gian | Chủ đề | Gate / Kết quả bàn giao |
|---|---|---|---|---|
| Sprint 01 | Tuần 1 | 25/7 – 01/8 | Đề tài, BRIEF, PRD, vai trò, Git workflow | ✅ **Gate 01** — chốt đề tài + BRIEF + PRD |
| Sprint 02 | Tuần 2 | 02/8 – 08/8 | **Dữ liệu thuốc + OCR/Vision + context base + skeleton** | **Gate 02** — có dữ liệu thuốc thật trong repo, spike vision có số đo, CI xanh |
| Sprint 03 | Tuần 3 | 09/8 – 15/8 | **Backend lõi**: phác đồ → duyệt → sinh lịch → nhắc | **Gate 03** — luồng "duyệt phác đồ → nhắc đúng giờ" chạy được end-to-end |
| Sprint 04 | Tuần 4 | 16/8 – 22/8 | **Agent + safety + escalation + dashboard** | **Gate 04** — 3 tính năng AI đạt ngưỡng chỉ số trong `eval/` |
| Sprint 05 | Tuần 5 | 23/8 – 29/8 | **Tích hợp, deploy, demo, pitch** | **Gate 05** — live URL + video demo + pitch deck + đủ deliverables |

> Ngày bắt đầu/kết thúc Sprint 02–05 là suy ra từ Tuần 1 (25/7–1/8). `[CẦN CHỐT: PM xác nhận lại mốc chính xác của Sprint 05 theo deadline nộp bài]`

## Sprint 01 — Tuần 1 (đã xong) ✅

**Đã đạt:** chốt đề tài VMEC-04; research thị trường (MediSafe, Apple Health, app Max, app Vinmec); BRIEF + PRD hoàn chỉnh; phân vai trò; Git workflow + CI (ruff + pytest).

**Kết luận quan trọng:** chưa có sản phẩm nào ghép trọn vòng khép kín *đơn duyệt → nhắc → xác nhận có bằng chứng → escalate → bác sĩ duyệt lại*. Đây là điểm khác biệt của đề tài.

Chi tiết: [`./sprints/sprint-01.md`](./sprints/sprint-01.md)

## Sprint 02 — Tuần 2 (đang chạy) 🔄

**Sprint Goal:** Giải quyết **rủi ro số 1 của dự án** (dữ liệu thuốc cho RAG) và có được số đo thật cho bài toán vision, đồng thời dựng xong context base + skeleton để Sprint 03 code được ngay.

**Trọng tâm:**
- Dữ liệu thuốc: tìm nguồn / crawl, chuẩn hoá theo `data pharmacy/schema.json`, commit lên repo
- Vision: research OCR trong y tế, chốt metric (bounding box vs segmentation), spike model đếm viên thuốc
- Form bác sĩ nhập đơn mô phỏng + form khảo sát sức khoẻ hằng ngày
- Skeleton FastAPI + docker-compose (Postgres + pgvector), CI xanh
- Context base: `/specs`, `/adrs`, `/tasks`, `/planning` (file này)

Chi tiết: [`./sprints/sprint-02.md`](./sprints/sprint-02.md)

## Sprint 03 — Tuần 3 (dự kiến)

**Sprint Goal:** Luồng xương sống chạy được: bác sĩ tạo phác đồ → duyệt → hệ thống sinh `dose_event` → nhắc đúng giờ → bệnh nhân xác nhận.

- `FEAT-001` Tạo & duyệt phác đồ (HITL) — kèm preview timeline
- `FEAT-002` Sinh lịch nhắc & dose window ±30'
- `FEAT-003` Cron 1 phút, nhắc 3 cấp độ, đóng window → `MISSED`
- `FEAT-011` Audit log
- `INFRA-02` Schema DB + Alembic
- FE: màn hình bác sĩ (tạo/duyệt phác đồ), màn hình bệnh nhân (danh sách liều + xác nhận)

**Điều kiện ra khỏi sprint:** demo được end-to-end trên máy local, có test cho logic sinh lịch và dose window.

## Sprint 04 — Tuần 4 (dự kiến)

**Sprint Goal:** Ba tính năng AI hoạt động và **đạt ngưỡng chỉ số đo được**, không chỉ "chạy được".

- `FEAT-005` Phân loại hội thoại 4 nhãn (accuracy ≥ 85%)
- `FEAT-008` Safety layer (**recall ≥ 90–95%** — chỉ số quan trọng nhất)
- `FEAT-006` RAG trả lời có nguồn (0 ca bịa thông tin trên test set)
- `FEAT-004` Xác nhận ảnh hoàn chỉnh (2 lần → caregiver)
- `FEAT-007` Đánh giá mức nghiêm trọng theo ngữ cảnh thuốc
- `FEAT-009` Escalation + hàng đợi người thân
- `FEAT-010` Dashboard tuân thủ (tách tự khai vs có xác minh)

**Điều kiện ra khỏi sprint:** kết quả đánh giá được commit vào `eval/results/` — có bằng chứng, không nói miệng.

## Sprint 05 — Tuần 5 (dự kiến)

**Sprint Goal:** Sản phẩm chạy được trên môi trường thật, đủ deliverables để nộp và trình bày.

- Tích hợp 3 frontend với backend, sửa lỗi tích hợp
- `INFRA-04` Deploy (live URL)
- Kịch bản demo + quay video demo (dùng `TIME_OFFSET_FACTOR` để mô phỏng escalation nhanh)
- Pitch deck (`presentation/`)
- Hoàn thiện `eval/results/report.md`, `JOURNAL.md`, `WORKLOG.md`
- Buffer sửa lỗi

**Điều kiện ra khỏi sprint:** checklist deliverables trong [`../README.md`](../README.md) tick đủ.

## Đường găng (critical path)

```
Dữ liệu thuốc (TASK-001) ──> RAG FEAT-006 ──> Đánh giá mức nghiêm trọng FEAT-007 ──> Escalation FEAT-009
Duyệt phác đồ FEAT-001 ──> Sinh lịch FEAT-002 ──> Nhắc FEAT-003 ──> Xác nhận FEAT-004/005 ──> Dashboard FEAT-010
```

**Hai nút thắt lớn nhất — trượt cái nào là trượt cả dự án:**

1. **Dữ liệu thuốc (TASK-001).** Không có dữ liệu có nguồn → không có RAG → không có đánh giá mức nghiêm trọng theo ngữ cảnh → mất luôn điểm khác biệt cốt lõi của đề tài. Đây là lý do nó nằm ở Sprint 02 chứ không phải Sprint 04.
2. **Duyệt phác đồ (FEAT-001).** Chặn toàn bộ nhánh còn lại vì agent chỉ chạy trên phác đồ `approved` (ADR-0010).

## Rủi ro & phương án dự phòng

| Rủi ro | Ảnh hưởng | Dự phòng |
|---|---|---|
| Không tìm được nguồn dữ liệu thuốc đủ chất lượng | **Cao** — mất điểm khác biệt cốt lõi | Thu hẹp phạm vi: chọn 20–30 thuốc phổ biến của bệnh mãn tính, làm sâu và có nguồn rõ, thay vì làm rộng mà nông |
| Mô hình đếm viên thuốc không đủ chính xác | Trung bình | Đã có sẵn fallback trong thiết kế: 2 lần chụp → người thân duyệt (ADR-0011). Hệ thống vẫn chạy, chỉ tăng tỷ lệ rơi vào nhánh caregiver |
| LLM rate limit / hết quota giữa tuần demo | Cao | Cấu hình provider qua `.env` để đổi được nhanh; keyword layer của safety vẫn chạy khi LLM chết (ADR-0009) |
| 4 người kiêm nhiệm, có tuần bận việc khác | Trung bình | Mỗi người có backup trong `TEAM.md`; ưu tiên P0 trước, P2 sẵn sàng cắt |
| Dồn tích hợp vào tuần cuối | Cao | Tích hợp sớm từng phần trong Sprint 03–04, không để tuần 5 mới ghép |

---
**Lưu ý cho AI:** Khi được giao task, đối chiếu xem nó thuộc sprint nào và có nằm trên đường găng không. Task trên đường găng bị chặn → **báo ngay cho PM**, đừng im lặng làm việc khác.
