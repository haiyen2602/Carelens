# TASK-008: Bộ test set safety layer + danh sách redflag tiếng Việt

**Domain:** `safety`
**Owner:** Phạm Thành Đạt + AI
**Sprint:** sprint-02
**Status:** To Do
**Ưu tiên:** P0 · **Feature:** [`FEAT-008`](../specs/features.md#feat-008--safety-layer-song-song) · **Backlog item:** `INFRA-03`

## Mục tiêu (Goal)

Có **thước đo trước khi có code**: một bộ test set phát ngôn tiếng Việt có nhãn, cùng danh sách keyword redflag versioned trong repo, để Sprint 04 đo được recall của safety layer thay vì đoán. Recall của lớp này là **chỉ số quan trọng nhất của cả hệ thống** ([ADR-0009](../adrs/0009-safety-layer-dual-classifier.md)).

## Acceptance Criteria (AC)

- [ ] **Danh sách keyword redflag** lưu thành file versioned trong repo (không hardcode trong code — BR-6.4), mở rộng được mà không cần đổi code.
- [ ] Danh sách phủ đủ **10 nhóm redflag khởi tạo** ở [`business-rules.md`](../specs/business-rules.md) §6, mỗi nhóm có **nhiều cách nói dân dã** — không chỉ thuật ngữ y khoa (VD: "khó thở" ↔ "thở không nổi" ↔ "ngực nặng như có đá đè" ↔ "hụt hơi").
- [ ] Bao gồm cách nói của **người cao tuổi và từ địa phương** — đây là điểm ADR-0009 cảnh báo dễ thiếu nhất.
- [ ] **Test set tối thiểu 100 phát ngôn** có nhãn `redflag` / `not_redflag`, trong đó:
  - [ ] Ca redflag **nói thẳng** (VD: "tôi bị đau ngực")
  - [ ] Ca redflag **nói gián tiếp / lẫn trong câu chuyện khác** (VD: "tôi uống rồi, mà từ chiều thấy khó thở với tức ngực") — ca này keyword dễ trượt, LLM phải bắt
  - [ ] Ca **âm tính khó** (near-miss): nhắc tới từ nguy hiểm nhưng không phải cấp cứu (VD: "hôm trước bà hàng xóm bị đau ngực", "bác sĩ dặn nếu khó thở thì gọi") — dùng để đo false positive
  - [ ] Ca bình thường không liên quan
- [ ] Mỗi ca ghi rõ: phát ngôn · nhãn · nhóm redflag (nếu có) · nguồn/lý do gán nhãn.
- [ ] Test set ở **định dạng máy đọc được** (JSONL/CSV), chạy được bằng script, không phải bảng trong file Word.
- [ ] Có **script đo** chạy được một lệnh, in ra **recall / precision / false positive rate**, kết quả ghi vào `eval/results/`.
- [ ] Script chạy được **ở chế độ keyword-only** (không cần LLM, không cần API key) — để đo được ngay trong sprint này và để CI chạy được.
- [ ] Ghi rõ **ngưỡng phải đạt: recall ≥ 90–95%**, chấp nhận false positive ([ADR-0001](../adrs/0001-test-strategy.md)).
- [ ] Có `eval/README.md` giải thích: cấu trúc test set, cách thêm ca mới, cách chạy, ý nghĩa từng chỉ số.

## Context bắt buộc phải đọc trước khi làm (dành cho AI)

- [ ] [`/adrs/0009-safety-layer-dual-classifier.md`](../adrs/0009-safety-layer-dual-classifier.md) — kiến trúc 2 lớp OR, các ràng buộc bắt buộc
- [ ] [`/adrs/0001-test-strategy.md`](../adrs/0001-test-strategy.md) — quy ước `eval/`, ngưỡng chỉ số, "không assert cứng cho output LLM"
- [ ] [`/specs/business-rules.md`](../specs/business-rules.md) — §6 safety layer, §3 mức nghiêm trọng (BR-3.3)
- [ ] [`/specs/features.md`](../specs/features.md) — FEAT-008
- [ ] [`/specs/domains.md`](../specs/domains.md) — ranh giới `safety`, event `safety.redflag`
- [ ] [`AGENTS.md`](../AGENTS.md)

## Gợi ý chia subtask (AI tự cập nhật khi bắt đầu)

- [ ] Chốt **format** file keyword + file test set (bàn với Trương Quốc Trường để khớp cách code sẽ đọc ở Sprint 04)
- [ ] Xây danh sách keyword theo 10 nhóm, mỗi nhóm nhiều biến thể cách nói
- [ ] Viết 100+ ca test, cân đối 4 loại ca ở AC (đặc biệt đừng bỏ qua **near-miss** — đây là phần dễ làm ẩu nhất)
- [ ] Lấy thêm phát ngôn thật từ [`TASK-005`](./TASK-005-form-khao-sat-suc-khoe.md) nếu form đã có dữ liệu
- [ ] Viết script đo recall/precision/FPR ở chế độ keyword-only
- [ ] Chạy baseline keyword-only, ghi số vào `eval/results/` — đây là mốc so sánh cho Sprint 04
- [ ] Viết `eval/README.md`
- [ ] Review chéo nhãn với ít nhất 1 thành viên khác (chống thiên lệch của một người gán nhãn)

## Definition of Done

Áp dụng checklist chuẩn ở [`ADR-0005`](../adrs/0005-definition-of-done.md), **kèm checklist bổ sung cho task đụng AI và task đụng an toàn**. Tiêu chí riêng của task này:

- [ ] Có **số baseline keyword-only** commit trong `eval/results/` — không kết thúc task mà chưa có con số nào
- [ ] Nhãn của test set được review bởi người thứ hai
- [ ] Không dùng phát ngôn thật của bệnh nhân thật; mọi ca là mô phỏng hoặc đã ẩn danh hoàn toàn
- [ ] Trong `eval/README.md` ghi rõ quy tắc [ADR-0001](../adrs/0001-test-strategy.md): **mỗi ca bỏ sót redflag phát hiện về sau bắt buộc trở thành một test case mới trước khi fix**

## Ghi chú / trao đổi thêm

- Task này **không** implement safety layer — chỉ xây thước đo. Nhưng nó chặn việc đánh giá FEAT-008 ở Sprint 04, nên là P0.
- Baseline keyword-only rất có giá trị: nếu keyword đã đạt recall cao trên test set, ta biết chính xác LLM layer cần bù phần nào (các ca gián tiếp).
- False positive **được chấp nhận** — đừng tối ưu test set theo hướng giảm cảnh báo thừa. Nếu FPR quá cao, cách xử lý là cải thiện từng lớp, **không** đổi OR thành AND (ADR-0009).
- `[CẦN CHỐT]` Recall mục tiêu chốt ở 90% hay 95%? ADR đang ghi khoảng — cần một con số cụ thể để script biết pass/fail. QA đề xuất, PM + Architect chốt.

---
**Điều hướng:** [Sprint 02](../planning/sprints/sprint-02.md) · [Backlog](../planning/backlog.md) · [Tasks](./)
