# TASK-002: Spike — metric & model đếm viên thuốc từ ảnh

**Domain:** `photo-verification`
**Owner:** Nguyễn Minh Đạt + AI
**Sprint:** sprint-02
**Status:** To Do
**Ưu tiên:** P0 · **Feature:** [`FEAT-004`](../specs/features.md#feat-004--xác-nhận-liều-bằng-ảnh)
**Loại:** Spike (time-boxed — **tối đa 2 ngày công**)

## Mục tiêu (Goal)

Trả lời bằng **số thật**, không phải bằng cảm giác: bài toán "đếm viên thuốc trong ảnh" đo bằng metric nào, cách tiếp cận nào khả thi trong 5 tuần, và độ chính xác hiện tại là bao nhiêu. Kết quả spike là căn cứ để Sprint 03–04 code FEAT-004 hoặc quyết định dựa hẳn vào fallback người thân duyệt.

## Acceptance Criteria (AC)

- [ ] **Chốt metric** cho bài toán, ghi rõ lý do chọn — bounding box detection (mAP / count accuracy) vs segmentation (IoU) vs regression đếm trực tiếp.
- [ ] Chốt **metric nghiệm thu chính** ở mức nghiệp vụ: *count accuracy* — tỷ lệ ảnh mà số viên dự đoán **khớp chính xác** số viên thật (không phải mAP, vì nghiệp vụ chỉ cần đúng/sai số viên).
- [ ] Có **tập ảnh thử nghiệm tối thiểu 50 ảnh** tự chụp (viên rời, viên trong vỉ, nhiều loại lẫn nhau, nền sáng/tối), có nhãn số viên thật.
- [ ] Chạy được **ít nhất 2 cách tiếp cận** để so sánh (VD: model detection sẵn có / fine-tune nhẹ / gọi vision API của LLM) — mỗi cách có số đo trên cùng tập ảnh.
- [ ] Có **bảng kết quả** trong `eval/results/` : cách tiếp cận × count accuracy × thời gian suy luận × chi phí/ảnh.
- [ ] Có **kết luận rõ ràng**: chọn cách nào cho MVP, ngưỡng confidence để coi là "khớp", và trường hợp nào bắt buộc rơi về fallback người thân.
- [ ] Ghi rõ **giới hạn đã biết** (VD: không đếm được viên xếp chồng, không đọc được vỉ bị che).

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`/specs/features.md`](../specs/features.md) — FEAT-004
- [ ] [`/adrs/0011-photo-verification-fallback.md`](../adrs/0011-photo-verification-fallback.md) — fallback đã có sẵn, spike **không** được chặn đường này
- [ ] [`/adrs/0001-test-strategy.md`](../adrs/0001-test-strategy.md) — ngưỡng đánh giá & quy ước `eval/`
- [ ] [`/specs/domains.md`](../specs/domains.md) — `photo-verification`, event `photo.verified`
- [ ] [`AGENTS.md`](../AGENTS.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Research nhanh: OCR/vision trong bệnh viện & dược phẩm — 2–3 ví dụ thực tế cụ thể (theo kế hoạch tuần trong `JOURNAL.md`)
- [ ] Chuẩn bị tập ảnh 50 ảnh + file nhãn (`eval/` , không commit ảnh bệnh nhân thật — chỉ ảnh tự dàn dựng)
- [ ] Dựng script đánh giá dùng chung cho mọi cách tiếp cận (một lệnh → ra bảng số)
- [ ] Thử cách tiếp cận A, ghi số
- [ ] Thử cách tiếp cận B, ghi số
- [ ] Viết `eval/results/` báo cáo + README giải thích bài toán và ý nghĩa từng con số
- [ ] Trình bày kết luận cho team, cập nhật FEAT-004 / ADR-0011 nếu spike làm đổi quyết định

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md), **kèm checklist bổ sung cho task đụng AI**. Tiêu chí riêng của task này:

- [ ] Spike **kết thúc bằng một quyết định được ghi lại**, không kết thúc mở
- [ ] Số đo được commit vào `eval/results/` (bằng chứng, không nói miệng)
- [ ] Code spike được đánh dấu rõ là code thử nghiệm (không lẫn vào `src/` production)
- [ ] Không commit ảnh có mặt người / thông tin nhận dạng

## Ghi chú / trao đổi thêm

- **Rủi ro đã ghi trong sprint:** quá 2 ngày công vẫn chưa có số → **dừng spike**, chốt metric tạm và ghi rõ giới hạn. Fallback caregiver đã có sẵn ([ADR-0011](../adrs/0011-photo-verification-fallback.md)) nên dự án không sụp vì spike này.
- Spike này **không** phải implement FEAT-004. Không code luồng chụp lại 2 lần, không code API — chỉ đo và kết luận.
- `[CẦN CHỐT]` Ngưỡng count accuracy tối thiểu để dám dùng vision trong demo (đề xuất ≥ 80% trên tập ảnh dàn dựng) — Team Lead + QA chốt sau khi có số đầu tiên.

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Backlog](../planning/backlog.md) · [Tasks](./)
