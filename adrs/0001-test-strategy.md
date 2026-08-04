# ADR-0001: Test-Driven / Test Strategy

**Status:** Accepted
**Ngày:** 2026-08-04 (viết thành ADR; quyết định CI `ruff + pytest` đã chốt tại `WORKLOG.md` 2026-07-26)
**Người đề xuất:** Phạm Thành Đạt (QA/Tester) · Trương Quốc Trường (Tech Leader)
**Người duyệt:** Nguyễn Minh Đạt (Team Leader/Architect) — `[chờ xác nhận trong buổi review đầu Sprint 02]`

## Bối cảnh (Context)

Khi cả team và AI cùng code, cần một "đích đến" rõ ràng để biết implementation đã đúng hay chưa, tránh việc AI hoặc dev tự diễn giải yêu cầu theo cách khác nhau.

## Quyết định (Decision)

Team ưu tiên viết test (unit / integration / e2e) hoặc Acceptance Criteria (AC) rõ ràng **trước khi** implementation, tuỳ theo mức độ phức tạp của task.

- Task có logic nghiệp vụ quan trọng → viết test trước hoặc song song với code, không viết sau cùng.
- Mọi task đều phải có AC rõ ràng trong `/tasks/{id}.md` trước khi bắt đầu code, kể cả khi không viết test trước.

## Vì sao thân thiện với AI + Team

- Agent có "đích đến" rõ ràng: biết chính xác thế nào là đúng, thế nào là sai.
- Agent có thể tự vận hành vòng lặp: tự code → tự chạy test → tự sửa lỗi, giảm số lần cần con người can thiệp.
- Review nhẹ hơn vì reviewer nhìn vào test pass/fail thay vì phải đọc từng dòng logic để đoán ý đồ.

## Hệ quả (Consequences)

**Tích cực:**
- Giảm hiểu lầm giữa yêu cầu và implementation.
- Regression được phát hiện sớm.

**Đánh đổi / rủi ro:**
- Tốn thời gian đầu để viết test/AC; cần kỷ luật để không bỏ qua bước này khi deadline gấp.

## Áp dụng cụ thể cho VMEC-04

### Công cụ

| Loại | Công cụ | Chạy ở đâu |
|---|---|---|
| Unit / integration | `pytest` | local + CI (`.github/workflows/ci.yml`) |
| Lint / format | `ruff` | local + CI |
| Đánh giá chất lượng AI (accuracy/recall) | script riêng, kết quả vào `eval/results/` | chạy tay khi đổi prompt/model |

CI chạy `ruff` + `pytest` trên **mọi push và PR vào `main`** — PR không pass CI thì không merge (xem ADR-0005).

### Ba loại test bắt buộc theo tính chất task

1. **Test logic nghiệp vụ tất định** (sinh `dose_event`, dose window, chuyển trạng thái liều, phân quyền theo role) → **viết test trước hoặc song song với code**. Đây là phần bắt buộc có unit test.
2. **Test tích hợp qua contract** (API trả đúng shape trong [`../specs/api-contracts.md`](../specs/api-contracts.md), mã lỗi đúng bảng §10) → integration test với FastAPI `TestClient`.
3. **Đánh giá đầu ra LLM/Vision** (phân loại 4 nhãn, recall safety layer, đếm viên thuốc) → **không dùng assert cứng** vì output không tất định. Thay bằng **bộ test set + ngưỡng chỉ số**, kết quả lưu vào `eval/results/`:

   | Thành phần | Chỉ số | Ngưỡng phải đạt |
   |---|---|---|
   | Safety layer | **recall** | **≥ 90–95%** (chỉ số quan trọng nhất) |
   | Phân loại hội thoại 4 nhãn | accuracy | ≥ 85% `[CẦN CHỐT cùng test set]` |
   | Đếm viên thuốc | `[CẦN CHỐT sau TASK-002]` | |

### Quy tắc riêng cho phần AI

- **Mock LLM/Vision trong unit test** — không gọi API thật trong `pytest` (chậm, tốn tiền, không tất định). Gọi thật chỉ trong script đánh giá ở `eval/`.
- **Test safety layer phải test được keyword layer độc lập với LLM layer** — bao gồm ca "LLM lỗi/timeout nhưng keyword vẫn bắt được redflag" (BR-6.3).
- Mỗi bug về an toàn (bỏ sót redflag, agent bịa thông tin thuốc) → **bắt buộc thêm một test case vào test set** trước khi fix.

### Mọi task phải có AC

Mọi task trong `/tasks` phải có Acceptance Criteria cụ thể, kiểm chứng được **trước khi bắt đầu code**, kể cả task không viết test trước. Task thiếu AC → AI phải hỏi lại, không tự suy diễn (xem `AGENTS.md` §2).

## Câu chốt

> Test là hợp đồng hành vi của hệ thống. Với phần AI không tất định, **ngưỡng chỉ số trên test set** chính là hợp đồng đó.
