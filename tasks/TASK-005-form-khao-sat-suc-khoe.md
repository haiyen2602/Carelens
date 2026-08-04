# TASK-005: Form khảo sát sức khoẻ bệnh nhân hằng ngày

**Domain:** `conversation`
**Owner:** Nguyễn Hải Yến + AI
**Sprint:** sprint-02
**Status:** To Do
**Ưu tiên:** P1 · **Feature:** [`FEAT-005`](../specs/features.md#feat-005--hội-thoại-tự-nhiên--phân-loại-4-nhãn), [`FEAT-008`](../specs/features.md#feat-008--safety-layer-song-song)

## Mục tiêu (Goal)

Có form khảo sát sức khoẻ hằng ngày cho bệnh nhân — vừa là kênh thu thập trạng thái để agent theo dõi, vừa là **nguồn dữ liệu phát ngôn tiếng Việt thật** để nuôi bộ test phân loại hội thoại và safety layer.

## Acceptance Criteria (AC)

- [ ] Form thu được: tình trạng dùng thuốc hôm nay, triệu chứng/tác dụng phụ gặp phải, mức độ khó chịu, ghi chú tự do.
- [ ] Có **ô trả lời tự do bằng tiếng Việt** — không chỉ radio/checkbox. Đây là phần quan trọng nhất: FEAT-005 cần phân loại được câu nói tự nhiên.
- [ ] Thiết kế cho **người cao tuổi**: chữ lớn (tối thiểu 16px, ưu tiên 18px), tương phản đạt WCAG AA, vùng bấm ≥ 44×44px, ít bước nhất có thể.
- [ ] Form hoàn thành được trong **dưới 1 phút** — đo thật với 1 người thử, không đoán.
- [ ] Mọi câu hỏi triệu chứng dùng **từ ngữ dân dã**, không dùng thuật ngữ y khoa (VD: "thấy khó thở không?" thay vì "có dyspnea?").
- [ ] Có mục nhập triệu chứng phủ được **nhóm redflag khởi tạo** ở [`business-rules.md`](../specs/business-rules.md) §6 (khó thở, đau ngực, ngất, co giật...) — để [`TASK-008`](./TASK-008-test-set-safety-layer.md) dùng làm đầu vào.
- [ ] Accessibility: label đúng, đi được bằng bàn phím, screen reader đọc được lỗi và trạng thái.
- [ ] Trên form ghi rõ **đây không phải kênh cấp cứu** — có hướng dẫn liên hệ cấp cứu khi triệu chứng nặng (BR-7.4).

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`/specs/features.md`](../specs/features.md) — FEAT-005, FEAT-008
- [ ] [`/specs/business-rules.md`](../specs/business-rules.md) — §5 phân loại hội thoại, §6 safety layer, BR-7.4
- [ ] [`/specs/user-roles.md`](../specs/user-roles.md) — role `patient`
- [ ] [`/adrs/0009-safety-layer-dual-classifier.md`](../adrs/0009-safety-layer-dual-classifier.md)
- [ ] [`/specs/api-contracts.md`](../specs/api-contracts.md)
- [ ] [`AGENTS.md`](../AGENTS.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Chốt bộ câu hỏi cùng QA (Phạm Thành Đạt) để khớp với test set safety layer
- [ ] Viết lại toàn bộ câu hỏi bằng ngôn ngữ dân dã, tránh thuật ngữ y khoa
- [ ] Dựng form + ô trả lời tự do
- [ ] Áp style cho người cao tuổi (font, tương phản, kích thước vùng bấm)
- [ ] Thêm khối cảnh báo "không phải kênh cấp cứu" + hướng dẫn liên hệ
- [ ] Rà accessibility + đo thời gian hoàn thành với 1 người thử thật
- [ ] Bàn giao các phát ngôn thu được cho TASK-008 làm dữ liệu test

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md). Tiêu chí riêng của task này:

- [ ] Có kết quả thử với người thật (thời gian hoàn thành + nhận xét), ghi lại — không chỉ tự đánh giá
- [ ] Không dùng dữ liệu sức khoẻ thật của người thật khi commit ví dụ; dữ liệu mẫu là dữ liệu mô phỏng
- [ ] QA xác nhận bộ câu hỏi dùng được cho test set safety layer

## Ghi chú / trao đổi thêm

- Form này **không** tự đánh giá mức nghiêm trọng và **không** tự escalate — đó là FEAT-007/FEAT-008 ở sprint sau. Ở đây chỉ thu dữ liệu đúng và an toàn.
- Ô trả lời tự do là phần có giá trị lâu dài nhất: câu trả lời thật của người Việt khó mô phỏng bằng cách ngồi tự nghĩ ra.
- `[CẦN CHỐT]` Form gửi hằng ngày vào thời điểm nào, và có gắn với `dose_event` cụ thể hay độc lập theo ngày? — PM chốt trong [`TASK-006`](./TASK-006-chot-workflow-he-thong.md).

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Backlog](../planning/backlog.md) · [Tasks](./)
