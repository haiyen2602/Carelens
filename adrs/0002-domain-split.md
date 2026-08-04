# ADR-0002: Domain Split (Microservice / Modular Monolith Hybrid)

**Status:** Accepted
**Ngày:** 2026-08-04
**Người đề xuất:** Nguyễn Minh Đạt (Architect)
**Người duyệt:** Trương Quốc Trường (Tech Leader) — `[chờ xác nhận đầu Sprint 02]`

## Bối cảnh (Context)

Khi nhiều người + nhiều AI agent cùng làm việc trên một codebase lớn, nếu không có ranh giới rõ ràng, mọi người (và AI) sẽ phải đọc/hiểu toàn bộ hệ thống để làm một thay đổi nhỏ — chậm, dễ conflict, dễ sai.

## Quyết định (Decision)

Chia hệ thống theo domain rõ ràng. Có thể triển khai dưới dạng **Microservice** hoặc **Modular Monolith** (hybrid), tuỳ quy mô dự án — nhưng ranh giới domain trong code phải rõ ràng như nhau ở cả hai kiểu triển khai.

### Lựa chọn cho VMEC-04: **Modular Monolith**

Với timeline **5 tuần** và team **4 người kiêm nhiệm**, VMEC-04 triển khai **một service FastAPI duy nhất** (kèm 1 cron job trong cùng container), chia module theo domain:

```
src/
├── agents/        # LangGraph: graph.py, state.py, nodes/, tools/
├── api/           # routes theo role: doctor/, patient/, caregiver/
├── services/      # prescription/, scheduling/, safety/, escalation/, reporting/, audit/
├── models/        # Pydantic schema + DB model
├── config.py
└── main.py
```

**Ranh giới bắt buộc (dù cùng một process):**

- Module domain A **không import trực tiếp** hàm nội bộ của domain B — chỉ gọi qua interface/DTO đã khai báo trong [`../specs/api-contracts.md`](../specs/api-contracts.md) §8.
- Mỗi domain có một chủ sở hữu dữ liệu duy nhất; domain khác **không truy vấn thẳng bảng** của domain khác.
- Event nội bộ (`scheduling.dose_due`, `safety.redflag`, …) định nghĩa như contract thật ngay từ đầu, để sau này tách service không phải viết lại (xem `api-contracts.md` §9).

**Vì sao không chọn Microservice ngay:** 4 người / 5 tuần không đủ ngân sách vận hành cho nhiều service (deploy, monitoring, tracing, contract test giữa các service). Ranh giới domain sạch trong monolith cho ta gần hết lợi ích về chia context và chia việc, mà không phải trả chi phí vận hành đó.

> Danh sách domain cụ thể: xem [`../specs/domains.md`](../specs/domains.md) — `auth`, `prescription`, `scheduling`, `conversation`, `photo-verification`, `drug-knowledge`, `safety`, `escalation`, `notification`, `reporting`, `audit`.
> Reviewer bắt buộc theo domain: xem [`../TEAM.md`](../TEAM.md) §2.

## Vì sao thân thiện với AI + Team

- Mỗi member (+ AI) phụ trách một domain → làm việc song song dễ hơn, ít khoá lẫn nhau.
- Giảm phụ thuộc, ít conflict code khi nhiều người commit cùng lúc.
- Agent chỉ cần context của service/module đang làm → giảm "over-context" (không phải nạp toàn bộ hệ thống vào context window).

## Hệ quả (Consequences)

**Tích cực:**
- Scale team + AI dễ dàng hơn.
- Onboard thành viên/agent mới nhanh hơn (chỉ cần hiểu 1 domain).

**Đánh đổi / rủi ro:**
- Cần đầu tư vào contract rõ ràng giữa các domain (xem ADR-0003), nếu không sẽ phát sinh phụ thuộc ngầm.
- Với Microservice: thêm chi phí vận hành (deploy, monitoring nhiều service).
- **Rủi ro riêng của Modular Monolith:** vì cùng một process nên rất dễ "lỡ tay" import chéo giữa các domain và làm nhoè ranh giới. → Phải soi trong review theo domain (`TEAM.md` §2); nếu tái diễn thì bổ sung rule lint chặn import chéo.

## Câu chốt

> Chia domain tốt = chia context tốt.
