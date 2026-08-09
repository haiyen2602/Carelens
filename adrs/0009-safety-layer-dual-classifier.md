# ADR-0009: Safety Layer — Dual classifier chạy song song (keyword OR LLM)

**Status:** Accepted
**Ngày:** 2026-08-04
**Người đề xuất:** Phạm Thành Đạt (phụ trách safety layer & phân loại hội thoại)
**Người duyệt:** Nguyễn Minh Đạt (Architect) · Nguyễn Hải Yến (PM) — `[chờ xác nhận đầu Sprint 02]`

## Bối cảnh (Context)

Bệnh nhân có thể nói ra triệu chứng nguy hiểm (khó thở, đau ngực, ngất, yếu liệt nửa người) **giữa một câu chuyện bình thường**, khi đang trả lời câu hỏi về việc uống thuốc — ví dụ: *"tôi uống rồi, mà từ chiều thấy khó thở với tức ngực"*.

Nếu để luồng phân loại chính (`phan_loai_hoi_thoai` — gán 4 nhãn Taken/Missed/Delayed/SideEffect) chịu trách nhiệm luôn việc phát hiện nguy hiểm, sẽ có hai vấn đề:

1. Nó đang tối ưu cho việc **phân loại đúng nhãn**, không phải cho việc **không bỏ sót triệu chứng**. Hai mục tiêu này cần hai ngưỡng khác nhau.
2. Nếu luồng chính lỗi, timeout, hoặc LLM trả về sai định dạng → **triệu chứng nguy hiểm bị bỏ sót cùng với nó**.

Trong ngữ cảnh y tế, bỏ sót một ca khó thở nghiêm trọng nguy hiểm hơn nhiều so với việc báo động thừa vài lần.

## Quyết định (Decision)

Xây **safety layer riêng, chạy song song và độc lập** với luồng hội thoại chính, gồm **hai lớp phát hiện kết hợp bằng OR**:

```
utterance ─┬─> keyword rules ──┐
           │                   ├─ OR ─> redflag → cắt luồng, escalate HIGH < 2 phút
           └─> LLM classifier ─┘
```

**Các ràng buộc bắt buộc:**

| # | Ràng buộc |
|---|---|
| 1 | **OR logic** — chỉ cần **một** lớp cờ đỏ là kích hoạt, không cần cả hai đồng ý. |
| 2 | Chạy trên **mọi** phát ngôn của bệnh nhân, kể cả khi không nằm trong ngữ cảnh xác nhận liều. |
| 3 | **Độc lập với luồng chính:** lỗi/độ trễ của `phan_loai_hoi_thoai` không được chặn safety layer, và ngược lại. |
| 4 | **LLM lỗi/timeout → keyword layer vẫn phải chạy và vẫn có hiệu lực** (BR-6.3). Không có chuyện "LLM chết thì safety chết theo". |
| 5 | Cờ đỏ → **luôn là `severity = HIGH`**, ghi đè mọi kết quả đánh giá của luồng chính (BR-3.3). |
| 6 | Danh sách keyword lưu thành **file versioned trong repo**, mở rộng được không cần đổi code (BR-6.4). |
| 7 | **Không role nào, kể cả `admin`, được tắt safety layer từ UI** (BR-6.5). |
| 8 | Mục tiêu **recall ≥ 90–95%** trên bộ test triệu chứng nghiêm trọng; **chấp nhận false positive**. |

Event `safety.redflag` có **ưu tiên xử lý cao nhất** trong `escalation` (xem [`../specs/api-contracts.md`](../specs/api-contracts.md) §9).

## Vì sao (Rationale)

**Vì sao hai lớp thay vì một:**
- *Chỉ keyword:* nhanh, rẻ, tất định, không bao giờ chết — nhưng không hiểu diễn đạt gián tiếp ("tôi thở không nổi", "ngực nặng như có đá đè").
- *Chỉ LLM:* hiểu ngữ cảnh và cách nói vòng vo — nhưng có độ trễ, có thể lỗi/rate-limit, và không tất định.
- Hai lớp bù đúng điểm yếu của nhau: keyword là **lưới an toàn luôn sống**, LLM là **lớp bắt các ca diễn đạt gián tiếp**.

**Vì sao OR chứ không phải AND hay voting:** AND/voting làm tăng precision nhưng **giảm recall** — đúng ngược với thứ ta cần. Trong y tế, một cảnh báo thừa khiến người thân bực mình; một cảnh báo bị bỏ sót có thể khiến bệnh nhân nhập viện muộn. Đánh đổi này đã được cả team thống nhất từ Tuần 1 (bài học trong `JOURNAL.md`).

**Vì sao song song chứ không nối tiếp sau luồng chính:** nối tiếp nghĩa là safety phụ thuộc vào việc luồng chính chạy xong và chạy đúng. Với một lớp có nhiệm vụ "không bao giờ bỏ sót", mọi phụ thuộc thêm đều là một điểm chết thêm.

## Vì sao thân thiện với AI + Team

- Safety là một module riêng (`src/services/safety/`) với một chỉ số duy nhất (recall) → AI biết rõ đích đến khi làm task này, và test độc lập được với phần còn lại.
- Keyword layer tất định → viết unit test bình thường được, không cần mock LLM.
- Ràng buộc "LLM chết thì keyword vẫn chạy" là một test case cụ thể AI phải viết, không phải một mong muốn mơ hồ.

## Hệ quả (Consequences)

**Tích cực:**
- Không có điểm chết đơn lẻ cho chức năng an toàn nhất của hệ thống.
- Recall cao — đúng chỉ số quan trọng nhất của sản phẩm.
- Đo được: recall trên test set là con số trong `eval/results/`, không phải cảm tính.

**Đánh đổi / rủi ro:**
- **False positive sẽ nhiều** → người thân có thể bị làm phiền và dần bỏ qua cảnh báo ("alarm fatigue"). Cần theo dõi tỷ lệ false positive thực tế; nếu quá cao, giải pháp là **cải thiện chất lượng từng lớp**, không phải đổi OR thành AND.
- Mỗi phát ngôn gọi LLM **hai lần** (luồng chính + safety) → tăng chi phí và độ trễ. Chấp nhận; có thể tối ưu sau bằng cách cho keyword layer chặn sớm các ca hiển nhiên.
- Danh sách keyword tiếng Việt cần công sức xây và dễ thiếu (từ địa phương, cách nói của người cao tuổi) → phải mở rộng liên tục từ các ca thực tế bị bỏ sót, mỗi ca bỏ sót bắt buộc thành một test case mới (ADR-0001).
- Safety layer **không thay thế cấp cứu**: khi cờ đỏ, hệ thống hiển thị hướng dẫn liên hệ cấp cứu và escalate, không tự xử lý y khoa (BR-7.4).

## Câu chốt

> Báo thừa còn hơn bỏ sót. Lớp an toàn phải sống cả khi mọi thứ khác đã chết.
