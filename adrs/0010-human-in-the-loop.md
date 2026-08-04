# ADR-0010: Human-in-the-loop — Bác sĩ duyệt là cửa duy nhất kích hoạt agent

**Status:** Accepted
**Ngày:** 2026-08-04
**Người đề xuất:** Nguyễn Hải Yến (PM) · Trương Quốc Trường (Tech Leader — viết phần ràng buộc an toàn trong PRD)
**Người duyệt:** Cả team (chốt tại Gate 01, 2026-08-01)

## Bối cảnh (Context)

VMEC-04 tác động trực tiếp tới việc dùng thuốc của bệnh nhân mãn tính. Một agent tự quyết trong ngữ cảnh này có thể gây hại thật: sinh lịch sai từ đơn thuốc đọc nhầm, tự đổi giờ uống thuốc có yêu cầu khoảng cách liều nghiêm ngặt, hoặc tự trấn an bệnh nhân đang có triệu chứng nguy hiểm.

Ngoài rủi ro y khoa, còn có rào cản chấp nhận: **bác sĩ sẽ không dùng một hệ thống mà họ không kiểm soát được**. Bài học Tuần 1 ghi rõ — HITL là *điều kiện tiên quyết để bác sĩ tin dùng*, không phải một tính năng phụ (`JOURNAL.md`).

## Quyết định (Decision)

**Bác sĩ duyệt là cửa duy nhất để agent bắt đầu tác động lên bệnh nhân.** Cụ thể:

| # | Ràng buộc | Điểm enforce |
|---|---|---|
| 1 | Agent **chỉ** hoạt động trên phác đồ ở trạng thái `approved`. Phác đồ `draft`/`pending` không sinh `dose_event`, không nhắc, không chat theo liều. | `scheduling` từ chối input không `approved` → lỗi 422 |
| 2 | `POST /api/v1/prescriptions/{id}/approve` là **đường duy nhất** chuyển sang `approved`. Không domain nào được set trạng thái này bằng đường khác. | Contract §2 |
| 3 | Bác sĩ xem được **preview timeline** lịch nhắc **trước khi** duyệt (dry-run, không ghi DB). | `GET .../preview-schedule` |
| 4 | Mọi **đề xuất đổi lịch nhắc** của agent đều dừng lại ở node `hitl_duyet_lich` chờ bác sĩ duyệt — **agent không tự áp dụng** (FEAT-012). | Node LangGraph có nhánh dừng bắt buộc |
| 5 | Agent **không kê đơn, không đổi thuốc, không đổi liều, không chẩn đoán** trong mọi trường hợp. | BR-7.1 |
| 6 | Mọi hành động duyệt/từ chối/sửa/dừng ghi `audit_log` kèm actor + thời điểm; audit là **append-only**. | BR-7.5 |
| 7 | Chỉ bác sĩ **phụ trách bệnh nhân đó** mới được duyệt (kiểm tra cả role lẫn quan hệ liên kết). | BR-1.2, `user-roles.md` |

**Ngoại lệ duy nhất không cần chờ người:** escalation khi phát hiện triệu chứng nguy hiểm. Agent **được phép** cắt luồng, hiện overlay cấp cứu và báo khẩn ngay lập tức — vì hành động đó là *gọi người tới*, không phải *tự quyết y khoa thay người*.

## Vì sao (Rationale)

- **Giới hạn thiệt hại tối đa của một lỗi AI.** Nếu agent parse sai đơn thuốc, lỗi dừng lại ở màn hình preview của bác sĩ chứ không đi thẳng tới bệnh nhân.
- **Đặt trách nhiệm lâm sàng đúng chỗ.** Bác sĩ chịu trách nhiệm phác đồ; agent chịu trách nhiệm nhắc và thu bằng chứng. Ranh giới này phải rõ cả về kỹ thuật lẫn pháp lý.
- **Là điều kiện để sản phẩm được dùng thật.** Không có HITL, giá trị "dữ liệu tuân thủ đáng tin cho bác sĩ" sụp đổ vì bác sĩ không tin nguồn dữ liệu.
- **Nhất quán với chính nguyên tắc làm việc của team:** trong `AGENTS.md` §8, AI cũng không tự merge code. Cùng một triết lý, áp cho sản phẩm.

**Phương án bị loại:** *Auto-approve có ngưỡng confidence* (agent tự kích hoạt khi parse đơn với confidence cao). Bị loại vì confidence cao không đồng nghĩa đúng, và ta không có cách phát hiện ca sai còn lại — trong y tế, phần đuôi ấy mới là phần nguy hiểm.

## Vì sao thân thiện với AI + Team

- Agent có một ranh giới rõ ràng "được làm gì / phải dừng ở đâu" → không phải suy đoán trong từng tình huống.
- Nhánh HITL là một node tường minh trong LangGraph, thể hiện được trên sơ đồ và ghi audit được — không phải một quy ước ngầm nằm trong prompt.
- Ràng buộc "chỉ chạy trên `approved`" kiểm chứng được bằng unit test, nên AI tự verify được khi code.

## Hệ quả (Consequences)

**Tích cực:**
- Thiệt hại tối đa của một lỗi AI bị giới hạn ở phạm vi bác sĩ nhìn thấy trước.
- Bác sĩ có lý do để tin dữ liệu tuân thủ, vì họ kiểm soát đầu vào.
- Audit log + HITL là bằng chứng cần thiết nếu sau này sản phẩm đi vào môi trường y tế thật.

**Đánh đổi / rủi ro:**
- **Thêm ma sát cho bác sĩ:** mỗi phác đồ và mỗi đề xuất đổi lịch đều tốn một thao tác duyệt. → Bù lại bằng UX: preview timeline gọn, duyệt hàng loạt khi hợp lý, và **không** spam đề xuất vặt.
- **Chậm hơn:** đề xuất tối ưu lịch nhắc chỉ có hiệu lực sau khi bác sĩ vào duyệt — có thể là vài ngày. Chấp nhận được.
- Nếu bác sĩ bận và không duyệt, bệnh nhân không được nhắc → cần cảnh báo cho bác sĩ khi có phác đồ chờ duyệt quá lâu `[CẦN CHỐT: ngưỡng bao lâu]`.
- Có nguy cơ **duyệt cho có** (bác sĩ bấm duyệt mà không đọc). HITL chỉ có giá trị khi màn hình duyệt hiển thị đủ thông tin để phát hiện sai — đây là yêu cầu thiết kế UI, không chỉ là yêu cầu kỹ thuật.

## Câu chốt

> AI nhắc thuốc và thu bằng chứng. Bác sĩ vẫn là người quyết định điều trị — và hệ thống phải chặn về mặt kỹ thuật, không chỉ nhắc trong prompt.
