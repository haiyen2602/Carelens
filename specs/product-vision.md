# Product Vision — VMEC-04

> **Owner:** PM (Nguyễn Hải Yến) · **Cập nhật khi:** tầm nhìn/mục tiêu sản phẩm thay đổi
> Đây là nguồn sự thật về "chúng ta đang xây cái gì, cho ai, tại sao". AI và mọi thành viên phải đọc file này trước khi làm bất kỳ task nào liên quan đến sản phẩm.
> Nguồn gốc nội dung: BRIEF + PRD chốt tại Gate 01 (2026-08-01), xem `JOURNAL.md` Week 1 và `WORKLOG.md` 25/7–1/8.

**Tên sản phẩm:** VMEC-04 — AI Agent Nhắc Thuốc & Theo Dõi Tuân Thủ Điều Trị
**Một câu định vị:** AI Agent nhắc thuốc, xác nhận bằng ảnh + hội thoại tự nhiên, tạo **bằng chứng khách quan** về tuân thủ điều trị cho bệnh nhân mãn tính và cho bác sĩ.

## 1. Vấn đề đang giải quyết

1. **Bệnh nhân quên/uống sai thuốc.** Người cao tuổi nhiều bệnh nền (tim mạch, huyết áp, thận, gan) dùng nhiều loại thuốc ở nhiều khung giờ mỗi ngày → quên liều, uống trễ, uống sai loại, hoặc tự ý ngưng thuốc khi thấy đỡ. Với bệnh nhân sau đột quỵ, thiếu 1–2 liều đã có thể gây khó thở, ho, và căng thẳng cho cả gia đình.
2. **Bác sĩ ra quyết định lâm sàng trên dữ liệu sai.** Giữa hai lần tái khám, bác sĩ không có dữ liệu nào về việc bệnh nhân có thực sự uống thuốc hay không, phải dựa hoàn toàn vào lời kể → rủi ro tăng liều/đổi thuốc vì tưởng phác đồ không hiệu quả, trong khi thực tế bệnh nhân chưa dùng đủ liều.
3. **Giải pháp hiện có chỉ dừng ở mức thông báo.** App nhắc lịch, hộp chia thuốc thủ công, gọi điện nhắc (Calendar thủ công, app Max, Apple Health, MediSafe, app Vinmec) đều **không tạo được bằng chứng khách quan** rằng liều thuốc đã được uống, và không có vòng khép kín trả dữ liệu về cho bác sĩ.

> **Điểm mấu chốt cần giữ xuyên suốt khi trình bày sản phẩm:** vấn đề cốt lõi không phải "bệnh nhân quên thuốc" mà là **"bác sĩ ra quyết định lâm sàng trên dữ liệu sai"** (bài học Week 1, `JOURNAL.md`).

## 2. Đối tượng người dùng

| Mức | Vai trò | Ngữ cảnh sử dụng |
|---|---|---|
| Primary | **Bệnh nhân** | Người cao tuổi nhiều bệnh nền dùng thuốc dài ngày; và người trẻ trong liệu trình ngắn hạn (VD: kháng sinh) dễ bỏ ngang. Dùng Mobile PWA. |
| Primary | **Bác sĩ** | Bác sĩ nội khoa/chuyên khoa quản lý nhiều bệnh nhân mãn tính, cần dữ liệu tuân thủ thật thay vì lời khai. Dùng web desktop. |
| Secondary | **Người thân (Caregiver)** | Con cái/người chăm sóc, cần biết sớm khi có bất thường mà không phải gọi giục liên tục. Dùng mobile. |

Chi tiết quyền hạn từng vai trò: xem [`user-roles.md`](./user-roles.md).

## 3. Mục tiêu sản phẩm

1. **Tạo bằng chứng tuân thủ khách quan** — mỗi liều thuốc có trạng thái xác định (Taken / Missed / Delayed / SideEffect) kèm bằng chứng (ảnh đã đối chiếu và/hoặc hội thoại có phân loại), không chỉ là "bệnh nhân bấm nút đã uống".
2. **Rút ngắn thời gian phát hiện bất thường** — từ "chờ tới lần tái khám kế tiếp" xuống còn phút/giờ, thông qua escalation theo mức nghiêm trọng tới người thân và bác sĩ.
3. **Không bao giờ bỏ sót triệu chứng nghiêm trọng** — safety layer chạy song song, ưu tiên recall hơn precision.
4. **Giữ bác sĩ ở trung tâm quyết định (Human-in-the-loop)** — agent chỉ hoạt động trên phác đồ đã được bác sĩ duyệt; mọi đề xuất thay đổi lịch nhắc phải qua bác sĩ phê duyệt.
5. **Mọi hành động của AI đều truy vết được** — audit log ghi reasoning, confidence, nguồn RAG, để bác sĩ tin dùng và để truy vết sự cố.

## 4. Phạm vi (Scope)

### Trong phạm vi (In scope — MVP 5 tuần)

- Bác sĩ tạo phác đồ mô phỏng qua form trong hệ thống, và **duyệt** phác đồ (HITL) trước khi agent kích hoạt.
- Agent sinh lịch nhắc từ phác đồ đã duyệt (`dose_event`, dose window ±30 phút), nhắc 3 cấp độ tăng dần.
- Xác nhận liều bằng **ảnh** (vision đếm viên thuốc, đối chiếu phác đồ; tối đa 2 lần chụp lại → fallback người thân duyệt).
- Xác nhận liều bằng **hội thoại tự nhiên**, phân loại 4 nhãn: Taken / Missed / Delayed / SideEffect.
- **Đánh giá mức nghiêm trọng theo ngữ cảnh thuốc** bằng RAG trên dữ liệu thuốc có nguồn (pgvector) — không dùng rule cứng.
- **Safety layer song song** (keyword rules OR LLM) phát hiện triệu chứng nguy hiểm trong mọi phát ngôn của bệnh nhân.
- Escalation theo 3 mức (Nhẹ / Trung bình / Nghiêm trọng) tới người thân và/hoặc bác sĩ.
- Dashboard tuân thủ cho bác sĩ (phân biệt rõ **tuân thủ tự khai** vs **tuân thủ có xác minh**).
- Audit log đầy đủ cho mọi hành động của agent.

### Ngoài phạm vi (Out of scope — để AI không "làm thừa")

- **Không tích hợp EMR/HIS thật** của bệnh viện — phác đồ được nhập qua form mô phỏng.
- **Agent KHÔNG được kê đơn, đổi thuốc, đổi liều, hay chẩn đoán** — chỉ nhắc, thu bằng chứng, đánh giá mức nghiêm trọng và escalate.
- Không thay thế cấp cứu y tế: khi phát hiện dấu hiệu nguy hiểm, hệ thống hiện overlay cấp cứu + escalate, **không tự xử lý y khoa**.
- Không làm ở v1 (đẩy sang sprint sau): đồng bộ thiết bị đo (huyết áp, đường huyết), tích hợp nhà thuốc/đặt thuốc, thanh toán, tele-consult video, đa ngôn ngữ ngoài tiếng Việt.
- Không xây vector DB riêng (dùng pgvector trong PostgreSQL — xem ADR-0008).

## 5. Thành công được đo bằng gì (Success metrics)

| Chỉ số | Mục tiêu | Ghi chú |
|---|---|---|
| **Recall triệu chứng nghiêm trọng** (safety layer) | **≥ 90–95%** | Chỉ số quan trọng nhất của cả hệ thống. Chấp nhận false positive để không bỏ sót. |
| Accuracy phân loại hội thoại 4 nhãn | ≥ 85% `[CẦN CHỐT — Sprint 2, cùng bộ test set]` | Đo trên bộ hội thoại tiếng Việt tự tạo, lưu ở `eval/` |
| Độ chính xác đối chiếu ảnh (đếm viên thuốc) | `[CẦN CHỐT — sau TASK-002 khi có metric bounding box vs segmentation]` | |
| Độ trễ nhắc thuốc | < 1 phút so với giờ đã lên lịch | Ràng buộc thiết kế scheduler, xem ADR-0007 |
| Thời gian escalate mức Nghiêm trọng | < 2 phút | Từ lúc phát hiện redflag tới lúc người thân + bác sĩ nhận cảnh báo |
| Tỷ lệ liều có **bằng chứng xác minh** / tổng số liều | Càng cao càng tốt — là giá trị cốt lõi vs app nhắc lịch thường | Hiển thị trên dashboard bác sĩ |

## 6. Ràng buộc & giả định (Constraints & Assumptions)

**Ràng buộc:**
- **Thời gian: 5 tuần** (2026-07-25 → ~2026-08-29), team 4 người kiêm nhiệm nhiều vai trò — xem `TEAM.md` và [`../planning/roadmap.md`](../planning/roadmap.md).
- Tech stack đã chốt: FastAPI + LangGraph + PostgreSQL/pgvector + Next.js/PWA (xem ADR-0006).
- Chi phí LLM/hạ tầng ở mức tài khoản miễn phí/nhỏ → phải tiết kiệm số lần gọi LLM.
- Dữ liệu y tế cá nhân (PHI/PII) → bắt buộc mã hoá, phân quyền theo role, không commit dữ liệu thật lên repo.

**Giả định (nếu sai sẽ ảnh hưởng lớn tới sản phẩm):**
- **Rủi ro an toàn cao nhất:** nếu bộ dữ liệu thuốc không đủ/không có nguồn, agent có thể **"bịa" thông tin** (thành phần, tương tác, hướng dẫn dùng). → RAG trên dữ liệu có nguồn là ưu tiên kỹ thuật số 1 (xem `JOURNAL.md` Week 1, và TASK-001).
- Giả định bệnh nhân cao tuổi có thể tự chụp ảnh thuốc bằng điện thoại; nếu không → fallback nút bấm + người thân duyệt.
- Giả định bác sĩ chấp nhận thao tác duyệt phác đồ/duyệt đề xuất (HITL không bị coi là gánh nặng).
- Giả định hội thoại tiếng Việt tự do có thể phân loại đủ chính xác bằng LLM mà không cần fine-tune.

---
**Lưu ý cho AI:** Nếu một task được giao có vẻ đi ngược lại tầm nhìn hoặc phạm vi ở trên (đặc biệt các gạch đầu dòng "Out of scope" — ví dụ yêu cầu agent tự đổi liều thuốc), hãy **dừng lại và hỏi lại PM** thay vì tự suy diễn.
