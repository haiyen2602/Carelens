# Sprint 01 — Đề tài, BRIEF & PRD

**Thời gian:** 2026-07-25 → 2026-08-01
**Sprint Goal:** Chốt được đề tài, hiểu rõ vấn đề và người dùng, và có BRIEF + PRD hoàn chỉnh để làm nền cho toàn bộ 4 tuần còn lại.
**Trạng thái:** ✅ **Done — Gate 01 đạt (2026-08-01)**

> Sprint này diễn ra **trước khi** repo có cấu trúc `/tasks` — nên các việc dưới đây được ghi lại theo `WORKLOG.md` và `JOURNAL.md` thay vì có file task riêng. Từ Sprint 02 trở đi, mọi việc đều có file trong [`/tasks`](../../tasks/).

## Công việc trong Sprint

| # | Việc | Owner | Status | Output |
|---|---|---|---|---|
| 1 | Kickoff, thảo luận đề tài & pain point | Cả team | ✅ Done | Chốt hướng: AI nhắc thuốc & theo dõi tuân thủ điều trị |
| 2 | Chốt phân chia vai trò trong team | Cả team | ✅ Done | [`TEAM.md`](../../TEAM.md) §1 |
| 3 | Thiết lập Git workflow + CI | Trương Quốc Trường | ✅ Done | Branch `feature/fix/chore`, PR review qua Trường, CI `ruff` + `pytest` |
| 4 | Research app nhắc thuốc/sức khoẻ trên thị trường | Nguyễn Hải Yến | ✅ Done | So sánh Calendar thủ công, app Max, Apple Health, MediSafe |
| 5 | Trải nghiệm app Vinmec, đối chiếu đề tài | Trương Quốc Trường | ✅ Done | Ghi nhận app chưa có chatbot tương tự |
| 6 | Case study thực tế chăm người thân lớn tuổi dùng thuốc | Phạm Thành Đạt, Nguyễn Minh Đạt | ✅ Done | Cơ sở xác định pain point cho BRIEF |
| 7 | Viết BRIEF (vấn đề, người dùng, cách xoay xở hiện tại, điểm khác biệt, phạm vi, chỉ số, giả định rủi ro) | Nguyễn Hải Yến + M.Đạt + T.Đạt + Trường | ✅ Done | BRIEF VMEC-04 hoàn chỉnh |
| 8 | Viết PRD (10 tính năng theo vai trò, yêu cầu phi chức năng, ràng buộc an toàn, cắt phạm vi v1) | Cả team | ✅ Done | PRD VMEC-04 hoàn chỉnh |
| 9 | Review chéo BRIEF + PRD, thống nhất bản cuối | Cả team | ✅ Done | **Gate 01** |
| 10 | Khởi tạo Figma wireframe / UI flow | Nguyễn Hải Yến | 🔄 Carry over → Sprint 02 | Board Figma đã tạo, chưa có màn hình chi tiết |
| 11 | Checklist công việc Tuần 2 | Trương Quốc Trường | ✅ Done | Roadmap Tuần 2 |

## Kết luận nghiệp vụ quan trọng của Sprint

- **Chưa có sản phẩm nào trên thị trường ghép trọn vòng khép kín**: đơn duyệt → nhắc → xác nhận có bằng chứng → escalate → bác sĩ duyệt lại. Đây là điểm khác biệt của đề tài.
- Vấn đề cốt lõi **không phải** "bệnh nhân quên thuốc" mà là **"bác sĩ ra quyết định lâm sàng trên dữ liệu sai"**.

## Retro cuối Sprint

**Làm tốt:**
- [x] Hoàn thành đúng deadline research 28/7 và Gate 01 ngày 1/8 — không trượt mốc nào.
- [x] Chia việc song song hiệu quả: research thị trường, case study, và yêu cầu phi chức năng chạy cùng lúc.
- [x] Dùng câu chuyện thật của gia đình thành viên làm case study → pain point cụ thể, không chung chung.
- [x] Xác định sớm rủi ro số 1 (dữ liệu thuốc / agent bịa thông tin) ngay ở tuần đầu, thay vì phát hiện muộn.

**Cần cải thiện:**
- [ ] Cả tuần **chưa commit code nào** lên repo — toàn bộ output là tài liệu. Cần bắt đầu có code chạy được từ Sprint 02 để không dồn vào cuối.
- [ ] Dữ liệu thuốc cho RAG mới ở mức "đang tìm nguồn", chưa có gì trong repo — đúng là rủi ro lớn nhất nhưng chưa có hành động cụ thể trong tuần.
- [ ] Chưa chốt **số approve tối thiểu** trước khi merge (`TEAM.md` §2 vẫn đang để trống) — cần quyết trước khi có nhiều PR song song.
- [ ] Wireframe Figma bị trượt sang tuần sau.

**Hành động cho Sprint tiếp theo:**
- [ ] Ưu tiên cao nhất: có dữ liệu thuốc thật, chuẩn hoá, **commit vào repo** (TASK-001).
- [ ] Chốt số approve tối thiểu + luật merge còn thiếu trong `TEAM.md` §2 ngay đầu Sprint 02.
- [ ] Dựng skeleton FastAPI + CI xanh để Sprint 03 code feature được ngay, không mất thời gian setup.
- [ ] Viết context base (`/specs`, `/adrs`, `/tasks`, `/planning`) để AI và người mới có đủ ngữ cảnh làm việc.

---
**Điều hướng:** [Roadmap 5 tuần](../roadmap.md) · [Sprint 02](./sprint-02.md) · [Backlog](../backlog.md)
