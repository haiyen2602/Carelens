# ADR-0007: Scheduler — Cron 1 phút quét `dose_event`

**Status:** Accepted
**Ngày:** 2026-08-04
**Người đề xuất:** Trương Quốc Trường (Tech Leader — phụ trách backend & scheduler)
**Người duyệt:** Nguyễn Minh Đạt (Architect) — `[chờ xác nhận đầu Sprint 02]`

## Bối cảnh (Context)

Hệ thống phải nhắc thuốc **đúng giờ** cho nhiều bệnh nhân × nhiều liều/ngày, nhắc **3 cấp độ tăng dần** trong dose window ±30 phút, rồi **đóng window** và đánh dấu `MISSED` nếu không có phản hồi. Yêu cầu độ trễ nhắc **< 1 phút**.

Có hai cách làm phổ biến:

1. **Per-dose task:** khi duyệt phác đồ, tạo một task hẹn giờ (Celery/APScheduler) cho **từng liều** và từng cấp nhắc.
2. **Polling:** một job định kỳ quét bảng `dose_event` tìm liều đến hạn.

Ngoài ra, khi demo trước hội đồng, ta cần **mô phỏng nhanh** cảnh escalation — không thể chờ 30 phút thật để dose window hết hạn.

## Quyết định (Decision)

Dùng **một cron job chạy mỗi 1 phút**, quét bảng `dose_event` để tìm:

- liều **đến hạn nhắc** (`scheduled_at` tới, `reminder_level = 0`),
- liều **cần nhắc lại** (đã nhắc cấp 1/2, tới mốc cấp tiếp theo),
- liều **hết dose window** (`now > window_end`, còn `PENDING`) → chuyển `MISSED` và đưa vào luồng đánh giá mức nghiêm trọng.

**Không** tạo task hẹn giờ riêng cho từng liều thuốc.

Bổ sung một biến môi trường **`TIME_OFFSET_FACTOR`** (mặc định `1`) để rút ngắn mọi mốc thời gian khi demo — đây là **công cụ demo, không phải cơ chế nghiệp vụ**; phải không có tác dụng ở môi trường thật.

Tham số cụ thể (nguồn sự thật: [`../specs/business-rules.md`](../specs/business-rules.md) §2):

| Tham số | Giá trị |
|---|---|
| Chu kỳ quét | 1 phút |
| Dose window | ±30 phút |
| Mốc nhắc cấp 1/2/3 | T+0 / T+15' / T+30' `[ĐỀ XUẤT — CẦN CHỐT]` |

## Vì sao (Rationale)

- **Đơn giản hơn nhiều so với per-dose task:** không cần Celery + Redis/broker, không cần huỷ/tạo lại task khi bác sĩ sửa hoặc dừng phác đồ (chỉ cần đổi trạng thái row trong DB — lần quét kế tiếp tự nhìn thấy).
- **Đủ đáp ứng yêu cầu:** chu kỳ 1 phút cho độ trễ tối đa < 1 phút, đúng yêu cầu phi chức năng.
- **Chịu lỗi tốt hơn:** nếu service restart, per-dose task trong bộ nhớ sẽ mất; polling thì trạng thái nằm hết trong DB nên tự phục hồi ở lần quét kế tiếp.
- **Dễ debug và dễ test:** logic scheduler trở thành một hàm thuần "cho `now`, trả về danh sách hành động cần làm" — unit test được mà không cần chờ thời gian thật.
- **Chi phí vận hành thấp:** thêm một service (broker) là thêm một thứ có thể sập trong 5 tuần.

**Phương án bị loại:** Celery per-dose task — mạnh hơn khi scale lên hàng triệu liều và cần độ chính xác tới giây, nhưng ta không có yêu cầu đó, và cái giá là thêm broker + logic huỷ/tạo lại task mỗi khi phác đồ thay đổi.

## Vì sao thân thiện với AI + Team

- Chỉ một điểm vào duy nhất (`scan_due_doses(now)`) → AI biết chính xác nơi thêm logic nhắc mới, không rải rác nhiều nơi.
- Trạng thái nằm trong DB, không nằm trong bộ nhớ tiến trình → AI đọc bảng `dose_event` là hiểu được toàn bộ trạng thái hệ thống.
- Test được bằng cách truyền `now` giả, không cần `sleep` → vòng lặp tự-code-tự-test của AI chạy nhanh.

## Hệ quả (Consequences)

**Tích cực:**
- Không cần message broker; ít service để deploy và monitor.
- Sửa/dừng phác đồ chỉ là cập nhật DB — không phải dọn task treo.
- Tự phục hồi sau restart.

**Đánh đổi / rủi ro:**
- **Độ chính xác chỉ tới phút**, không tới giây. Chấp nhận được với nhắc uống thuốc.
- Quét toàn bảng mỗi phút sẽ tốn dần khi dữ liệu lớn → **bắt buộc có index trên `(status, scheduled_at)`** và chỉ quét cửa sổ thời gian gần.
- Nếu một lần quét chạy lâu hơn 1 phút, hai lần quét có thể chồng nhau → **phải chống chạy trùng** (lock hoặc cờ trong DB) và các hành động phải **idempotent** (không gửi nhắc 2 lần cho cùng một `reminder_level`).
- `TIME_OFFSET_FACTOR` là con dao hai lưỡi: nếu lỡ bật ở môi trường thật sẽ nhắc sai giờ → phải chặn ở config và ghi log `WARNING` rõ ràng khi khác `1`.

## Câu chốt

> Trạng thái để trong DB, để một cron job đơn giản đọc — đơn giản mà không mất tính đúng đắn, và tự phục hồi khi service khởi động lại.
