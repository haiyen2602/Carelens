# ADR-0011: Xác nhận bằng ảnh — 2 lần chụp lại rồi fallback người thân

**Status:** Accepted
**Ngày:** 2026-08-04
**Người đề xuất:** Nguyễn Minh Đạt (Architect — phụ trách vision) · Nguyễn Hải Yến (PM/UX)
**Người duyệt:** Cả team (chốt tại Gate 01, 2026-08-01)

## Bối cảnh (Context)

Giá trị cốt lõi phân biệt VMEC-04 với app nhắc lịch thông thường là **bằng chứng khách quan** rằng liều thuốc đã được uống — không chỉ là bệnh nhân bấm nút "đã uống". Cách làm: bệnh nhân chụp ảnh thuốc đã bày ra trước khi uống, vision tool đếm số viên và đối chiếu với phác đồ.

Vấn đề: người dùng chính là **người cao tuổi**. Ảnh sẽ thường xuyên không đạt — mờ, thiếu sáng, thuốc còn trong vỉ, chụp lệch, hoặc mô hình đếm sai. Nếu hệ thống cứ từ chối và bắt chụp lại mãi, bệnh nhân sẽ bỏ dùng app; nếu chấp nhận mọi ảnh, bằng chứng mất giá trị.

Cần một quy tắc dừng rõ ràng: **bao nhiêu lần thử là đủ, và sau đó thì làm gì?**

## Quyết định (Decision)

Luồng xác nhận bằng ảnh có **giới hạn 2 lần chụp lại**, sau đó chuyển sang **người thân duyệt**:

```
ảnh lần 1 ──khớp──> TAKEN (có xác minh)
   │ không khớp
   └─> yêu cầu chụp lại (lần 2) ──khớp──> TAKEN (có xác minh)
          │ không khớp
          └─> AWAITING_CAREGIVER: người thân duyệt trong 1 giờ
                 ├─ người thân đồng ý ──> TAKEN (caregiver_approved)
                 ├─ người thân từ chối ──> MISSED
                 └─ quá 1 giờ ──> [CẦN CHỐT: đề xuất MISSED + escalate MEDIUM]
```

**Quy tắc kèm theo:**

| # | Quy tắc |
|---|---|
| 1 | Tối đa **2 lần chụp lại** (tổng 3 lần gửi ảnh), sau đó **không bắt chụp nữa**. |
| 2 | Fallback **nút bấm** luôn khả dụng cho bệnh nhân không chụp được ảnh → `TAKEN (tự khai)`. |
| 3 | **`TAKEN (có xác minh)` và `TAKEN (tự khai)` là hai trạng thái khác nhau**, không được gộp trên dashboard bác sĩ (BR-4.1). |
| 4 | SLA người thân duyệt: **1 giờ**. |
| 5 | Mỗi lần gửi ảnh ghi `detected_count`, `expected_count`, `confidence` vào audit log (BR-4.2). |
| 6 | Ảnh là dữ liệu PHI → lưu có kiểm soát truy cập, **không commit vào repo**, không log dạng plain (BR-4.3). |
| 7 | Thông báo cho bệnh nhân phải **nói rõ vì sao không khớp** ("cháu đếm được 2 viên nhưng đơn là 1 viên"), không chỉ báo "thất bại". |

Xem contract: [`../specs/api-contracts.md`](../specs/api-contracts.md) §5 (`next_action` ∈ `NONE` / `RETAKE` / `CAREGIVER_REVIEW`).

## Vì sao (Rationale)

**Vì sao 2 lần mà không phải 1 hay 5:**
- 1 lần quá khắt khe — ảnh đầu tiên của người cao tuổi rất thường bị mờ/lệch, một lần trượt là bình thường chứ không phải dấu hiệu có vấn đề.
- 5 lần biến việc uống thuốc thành một bài kiểm tra. Người dùng sẽ bỏ, và ta mất cả bằng chứng lẫn người dùng.
- 2 lần cho một cơ hội sửa thật sự (đủ để bật đèn, bày lại thuốc ra mặt phẳng), rồi dừng — đủ để phân biệt "ảnh xấu" với "thật sự có gì đó không đúng".

**Vì sao fallback là người thân, không phải bác sĩ:**
- Bác sĩ không có thời gian duyệt từng ảnh của từng liều — dùng bác sĩ ở đây sẽ phá vỡ HITL ở nơi thật sự quan trọng (duyệt phác đồ).
- Người thân **có ngữ cảnh** ("hôm nay tôi ở cạnh, bố có uống"), phản hồi nhanh, và bản thân họ đã có nhu cầu theo dõi.
- Giữ được tính khách quan tương đối: người xác nhận **không phải** là chính bệnh nhân.

**Vì sao vẫn giữ nút bấm tự khai:** không có nó, bệnh nhân không chụp được ảnh sẽ không có cách nào ghi nhận liều, và dữ liệu tuân thủ trở thành rỗng thay vì kém tin cậy. Dữ liệu tự khai vẫn có ích — **miễn là bác sĩ biết đó là tự khai**, và đó là lý do quy tắc 3 tồn tại.

**Phương án bị loại:** *chỉ chấp nhận ảnh, không có fallback nào.* Bằng chứng sạch nhất về lý thuyết, nhưng sẽ khiến một phần đáng kể bệnh nhân cao tuổi không dùng được sản phẩm — đánh mất chính người dùng chính.

## Vì sao thân thiện với AI + Team

- Luồng có trạng thái hữu hạn và số lần thử cố định → mô hình hoá được thành state machine, unit test được đầy đủ mọi nhánh mà không cần chạy model vision thật.
- `attempt` / `max_attempts` / `next_action` nằm trong contract → FE biết chính xác phải hiển thị gì, không phải tự suy luận từ thông báo lỗi.
- Vision là phần dễ sai nhất; có quy tắc dừng rõ ràng nghĩa là chất lượng model kém cũng **không làm hệ thống treo** — chỉ làm tăng tỷ lệ rơi vào nhánh người thân duyệt, và tỷ lệ đó là một chỉ số đo được.

## Hệ quả (Consequences)

**Tích cực:**
- Bệnh nhân không bao giờ bị kẹt trong vòng lặp chụp lại vô hạn.
- Có bằng chứng phân tầng theo độ tin cậy (ảnh > người thân duyệt > tự khai) thay vì nhị phân có/không.
- Hệ thống vẫn chạy được ngay cả khi mô hình đếm viên thuốc còn yếu ở giai đoạn đầu.

**Đánh đổi / rủi ro:**
- **Đẩy việc sang người thân.** Nếu tỷ lệ ảnh không khớp cao, người thân sẽ bị quá tải và ngừng duyệt → cần theo dõi tỷ lệ rơi vào `AWAITING_CAREGIVER`; nếu cao thì phải cải thiện mô hình vision hoặc hướng dẫn chụp, **không** nới lỏng ngưỡng đối chiếu.
- **Ảnh không chứng minh được việc uống**, chỉ chứng minh thuốc đã được bày đúng số lượng. Đây là giới hạn cố hữu, phải nói thẳng khi trình bày sản phẩm — không được quảng cáo quá mức thành "bằng chứng đã uống".
- Bệnh nhân về lý thuyết có thể lách (chụp rồi không uống). Chấp nhận: mục tiêu là *tốt hơn hẳn lời khai*, không phải chống gian lận tuyệt đối.
- Metric mô hình đếm viên (bounding box vs segmentation) và ngưỡng confidence **chưa chốt** — phụ thuộc TASK-002.
- Người thân duyệt bằng cách xem ảnh → phải đảm bảo họ chỉ xem được ảnh của bệnh nhân mình liên kết (phân quyền theo quan hệ, không chỉ theo role).

## Câu chốt

> Hai lần thử rồi chuyển cho người thân. Bằng chứng phân tầng theo độ tin cậy, và bác sĩ luôn biết mình đang xem tầng nào.
