# TASK-022: Sửa thống kê tuân thủ và vòng đời liều thuốc

**Domain:** `medication`, `reporting`
**Owner:** Unassigned + AI
**Sprint:** Unplanned hotfix (không sửa retrospective Sprint 02 đã kết thúc)
**Status:** In Review

## Mục tiêu (Goal)

Màn hình Lịch sử của bệnh nhân báo tỷ lệ tuân thủ **88%** trong khi số thật là
**25%**. Nguyên nhân gốc không nằm ở phép tính hiển thị mà ở chỗ vòng đời liều
thuốc legacy chưa bao giờ được đóng lại: không có gì chuyển `PENDING` quá hạn
sang `MISSED`, nên liều bệnh nhân im lặng không đụng tới nằm lại vĩnh viễn và
bị mọi phép tính tuân thủ loại khỏi mẫu số.

Đo trên DB thật ngày 2026-08-31: 122/142 liều `PENDING` đã quá hạn.

## Acceptance Criteria (AC)

- [x] Liều còn `PENDING` sau khi đã sang ngày mới (giờ VN) được tự động chốt
  thành `MISSED`. Liều trong ngày đã qua `window_end` **không** bị chốt — bệnh
  nhân còn cơ hội xác nhận muộn. Job chạy lặp lại được, không đếm trùng.
- [x] Xác nhận "đã uống" sau `window_end` được ghi là `DELAYED`, do **backend**
  quyết định chứ không tin `body.status` của client. Nhãn `MISSED` do bệnh nhân
  chủ động chọn vẫn được tôn trọng nguyên vẹn.
- [x] Liều xác nhận muộn được **50%** điểm thưởng (không phải 0 như trước, cũng
  không phải đủ điểm). Ngày có liều muộn không được tính là ngày hoàn hảo cho
  thưởng chuỗi.
- [x] Mẫu số tuân thủ ở cả ba nơi (Lịch sử, Sức khoẻ, báo cáo bác sĩ) là **mọi
  liều đã qua `window_end`**, trừ `AWAITING_CAREGIVER` và `CANCELLED`.
- [x] `AWAITING_CAREGIVER` không bị tính là bỏ liều; được đếm riêng thành dòng
  "N liều chờ người thân duyệt", chỉ hiện khi > 0.
- [x] Nhật ký liều mở ra 5 dòng, có nút "Xem thêm N liều" (mỗi lần +20) và nút
  Thu gọn; các dòng gom theo ngày thay vì lặp lại ngày ở từng dòng.
- [x] Màn Lịch sử không còn gọi `GET /doses/{id}/photo-verifications` cho từng
  liều (147 request mỗi lần mở trang); thông tin đến kèm `GET /doses`.
- [x] Có script backfill chạy tay cho dữ liệu tồn đọng, **không** kích hoạt
  escalation, và ghi lại danh sách ID đã đổi.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [x] `AGENTS.md`, `GIT_WORKFLOW.md`
- [x] `/specs/business-rules.md` (BR-2.2 cửa sổ ±30 phút), `/specs/api-contracts.md` §3
- [x] `/adrs/0001-test-strategy.md`, `/adrs/0005-definition-of-done.md`, `/adrs/0011` (xác minh bằng ảnh)
- [x] `backend/services/scheduling/dose_state.py` — bộ máy trạng thái V2 đã hiện
  thực sẵn đúng ba quy tắc này; bản legacy mượn lại cùng định nghĩa để khi
  cutover sang V2 không bị lệch.

## Quyết định sản phẩm đã chốt (2026-08-31)

| Câu hỏi | Chốt | Lý do |
|---|---|---|
| Mốc phân định `DELAYED` / `MISSED` | Qua ngày mới giờ VN | Liều 20:00 mà 20:45 xác nhận là **muộn**, không phải bỏ. Chốt ngay khi hết cửa sổ sẽ cướp mất cơ hội xác nhận muộn. |
| `AWAITING_CAREGIVER` treo lâu | Treo mãi, đếm riêng | Lỗi ở người thân chưa duyệt, không phải bệnh nhân bỏ thuốc — chốt thành `MISSED` sẽ phạt nhầm người. |
| Điểm thưởng cho liều muộn | 50% | Để 0 thì bệnh nhân thấy xác nhận muộn "không được gì" và bỏ luôn — mất cả dữ liệu tuân thủ lẫn liều thuốc. |

## Thay đổi chính

**Backend**

- `backend/services/dose_lifecycle.py` (mới) — `qua_ngay_moi()`,
  `chot_lieu_qua_han()`, `chot_nhan_xac_nhan()`. Một nơi duy nhất trả lời "liều
  legacy nên mang nhãn nào theo đồng hồ", song song với `dose_state.py` của V2.
- `backend/services/escalation_scheduler.py` — job `dose_closeout`, interval 15
  phút. Cố ý **không** dùng cron sát nửa đêm: container restart đúng lúc đó thì
  cả ngày hôm ấy không bao giờ được chốt.
- `backend/api/dose_routes.py` — backend tự chốt nhãn; thêm `has_photo` qua một
  truy vấn `DISTINCT` thay cho N+1.
- `backend/services/photo_verification/verifier.py` — dùng chung hàm chốt nhãn
  thay vì biểu thức riêng.
- `backend/services/reward_ledger.py` — `_TRONG_SO_THUONG` (TAKEN 1.0, DELAYED
  0.5) thay cho danh sách "được/không được" thưởng.
- `backend/api/reporting_routes.py` — `_TRANG_THAI_VAO_MAU_SO` gồm cả `PENDING`.

**Frontend**

- `patient/history/page.tsx` — mẫu số đúng, dòng "chờ người thân", thu gọn +
  gom theo ngày, dùng `has_photo`.
- `patient/health/page.tsx` — mẫu số đúng.
- `lib/doses.ts` — thêm `hasPhoto`.

**Script**

- `scripts/backfill_dose_closeout.py` — có `--dry-run`, ghi báo cáo JSON.

## Giới hạn đã biết

- **Không có vết audit trong DB cho lần backfill.** Bảng `dose_event` (legacy)
  không có cột `status_reason`, còn `dose_event_log` của V2 đòi
  `dose_occurrence_id NOT NULL` nên không nhận được liều legacy. Thay vì thêm
  migration chỉ để phục vụ một lần chạy, script ghi danh sách ID ra file JSON
  (đã gitignore vì chứa dữ liệu bệnh nhân).
- **`has_photo` luôn `false` ở nhánh `dose_runtime_mode=v2`.** `photo_verification`
  trỏ tới bảng `dose_event`, không có đường nối sang `dose_occurrence`. Cùng lý
  do và cùng khuôn với hook điểm thưởng đã bị treo sẵn ở `_update_v2_dose_status()`.
- **Tử số của bác sĩ vẫn chỉ đếm `TAKEN`**, trong khi màn bệnh nhân đếm
  `TAKEN + DELAYED` là "đã hoàn thành". Task này chỉ sửa **mẫu số**; đổi tử số
  là một quyết định sản phẩm khác, chưa hỏi.

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md).

- [x] Test viết trước, xác nhận đỏ rồi mới sửa cho xanh.
- [ ] Có reviewer domain (Trương Quốc Trường).
- [x] Không commit dữ liệu bệnh nhân.

## Ghi chú / trao đổi thêm

Task tạo ngày 2026-08-31 từ báo cáo lỗi của người dùng về màn hình Lịch sử.
Phần `frontend/src/` thuộc vùng người khác phụ trách theo `GIT_WORKFLOW.md` —
người dùng xác nhận cho làm, cần báo lại người phụ trách frontend khi review.
