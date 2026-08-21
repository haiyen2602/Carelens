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
>
> *Bổ sung 2026-08-20:* điều này vẫn đúng khi trình bày **giá trị** của sản phẩm (pitch, demo, tài liệu kỹ thuật). Nhưng khi trình bày để **thu hút người dùng mới** (landing page), điểm vào là nỗi lo của người thân — xem §2.1. Hai cách nói này phải nhất quán, không mâu thuẫn: người thân yên tâm được *chính vì* bác sĩ có dữ liệu thật.

## 2. Đối tượng người dùng

| Mức | Vai trò | Ngữ cảnh sử dụng |
|---|---|---|
| Primary | **Bệnh nhân** | Người cao tuổi nhiều bệnh nền dùng thuốc dài ngày; và người trẻ trong liệu trình ngắn hạn (VD: kháng sinh) dễ bỏ ngang. Dùng Mobile PWA. |
| Primary | **Bác sĩ** | Bác sĩ nội khoa/chuyên khoa quản lý nhiều bệnh nhân mãn tính, cần dữ liệu tuân thủ thật thay vì lời khai. Dùng web desktop. |
| Secondary | **Người thân (Caregiver)** | Con cái/người chăm sóc, cần biết sớm khi có bất thường mà không phải gọi giục liên tục. Dùng mobile. |

Chi tiết quyền hạn từng vai trò: xem [`user-roles.md`](./user-roles.md).

### 2.1 Đối tượng tiếp cận (acquisition) — khác với người dùng chính

> Bổ sung 2026-08-20. Lý do: khi thiết kế landing page cần chốt "nói với ai", và câu trả lời đó **không trùng** với người dùng chính ở bảng trên.

**Người dùng chính (primary user)** — ai dùng sản phẩm hằng ngày — vẫn là **bệnh nhân + bác sĩ**, không đổi.

**Đối tượng tiếp cận (acquisition audience)** — ai là người nghe thông điệp marketing và mang sản phẩm vào gia đình — là **người thân (caregiver)**: người 25–40 tuổi, đi làm bận rộn, có cha/mẹ đang trong liệu trình điều trị dài ngày, không đủ thời gian ở cạnh để trực tiếp chăm sóc.

Lý do tách hai khái niệm này:

- Người dùng hằng ngày (bệnh nhân cao tuổi) thường **không phải** người chủ động đi tìm và cài đặt giải pháp.
- Bác sĩ là người khởi tạo phác đồ, nhưng thuyết phục bác sĩ đổi quy trình làm việc là bài toán bán hàng khác hẳn, không phù hợp với một landing page.
- Người thân là người vừa **có động cơ** (lo lắng, áy náy vì không ở cạnh), vừa **có khả năng hành động** (rành công nghệ, chủ động tìm giải pháp).

**Lời hứa dành riêng cho đối tượng tiếp cận** (dùng làm thông điệp chính của landing page): *biết sớm khi người thân có bất thường, mà không phải gọi điện giục liên tục.*

Lưu ý khi viết nội dung cho nhóm này: nói theo hướng **đồng hành**, không phải **giám sát**. Bệnh nhân còn minh mẫn có quyền biết và đồng ý với việc dữ liệu sức khoẻ của mình được người thân theo dõi.

**Ràng buộc đã chốt (2026-08-20): caregiver KHÔNG được tự nhập phác đồ.**

Chỉ bác sĩ mới được tạo và duyệt phác đồ. Ma trận quyền trong [`user-roles.md`](./user-roles.md) giữ nguyên (ô "Tạo phác đồ" của `caregiver` = ❌) — đây là quyết định có chủ đích, không phải thiếu sót.

Lý do: phác đồ là dữ liệu lâm sàng, người không có chuyên môn y khoa nhập vào sẽ phá vỡ nguyên tắc Human-in-the-loop ở §3.4 và mở thêm bề mặt rủi ro cho việc kiểm soát danh mục thuốc (FB-14).

**Hệ quả bắt buộc phải xử lý khi làm landing page:**

Sản phẩm có **cold-start** (trùng feedback FB-20): người thân đăng ký xong sẽ không có gì để xem cho tới khi bác sĩ kê đơn cho người bệnh trong hệ thống. Landing page **không được** hứa một luồng mà sản phẩm không chạy được — cụ thể là không dùng CTA kiểu "Đăng ký để theo dõi bố mẹ ngay".

Luồng vào đúng theo hiện trạng code (xem `backend/api/caregiver_routes.py`):

1. Người bệnh có tài khoản và được bác sĩ kê phác đồ (bác sĩ là điểm khởi đầu bắt buộc).
2. Người thân tự đăng ký — hiện đăng ký chỉ mở cho role `patient`, chưa có luồng đăng ký riêng cho `caregiver`.
3. Liên kết "người thân" được tạo bằng **lời mời giữa hai tài khoản người bệnh** (`POST /caregiver-links/invites`), và khi chấp nhận thì tự động tạo cả chiều ngược lại — quan hệ hai chiều, khác với quan hệ bác sĩ↔bệnh nhân vốn một chiều. Admin cũng tạo link được qua `/admin/links`.

Vì vậy thông điệp landing phải trung thực về vai trò của bác sĩ trong luồng, thay vì giấu đi để câu chuyện nghe gọn hơn.

**Đã chốt 2026-08-21 — CTA chính là "Đăng ký tài khoản".** Người thân tự đăng ký (hiện là tài khoản
`patient`), sau đó được liên kết qua lời mời. Kèm hai ràng buộc bắt buộc, không phải tuỳ chọn:

1. **Phải có màn hình rỗng được thiết kế tử tế.** Đăng ký xong mà thấy trang trắng là mất người dùng
   ngay tại đó — đúng vấn đề FB-20 nêu. Màn hình này cần nói rõ *đang thiếu gì* (chưa có phác đồ từ
   bác sĩ) và *làm gì tiếp* (mời người thân đã có tài khoản liên kết với mình, hoặc liên hệ bác sĩ
   đang điều trị).
2. **Landing phải nói rõ vai trò của bác sĩ** trong phần "cách hoạt động". Giấu đi thì câu chuyện gọn
   hơn nhưng người dùng vỡ mộng ngay sau khi đăng ký, và đó là kiểu mất niềm tin khó lấy lại — đặc
   biệt với sản phẩm y tế.

Đã cân nhắc và loại: CTA "mời bác sĩ của gia đình bạn" giải đúng gốc cold-start nhưng luồng đó chưa
tồn tại trong code, không kịp xây trước 2026-08-29. Nếu sản phẩm đi tiếp sau Demo Day thì đây là
hướng nên quay lại.

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
- **Giả định về đối tượng tiếp cận (§2.1), chưa kiểm chứng:** người thân bận rộn đủ lo lắng về việc tuân thủ điều trị của cha/mẹ để chủ động đi tìm và cài đặt một giải pháp — thay vì tiếp tục dùng cách gọi điện hỏi trực tiếp (miễn phí, đã quen). Cách kiểm chứng: 5–7 phỏng vấn 20 phút với người 25–40 tuổi có cha/mẹ dùng thuốc hằng ngày từ 3 tháng trở lên; hỏi về **hành vi đã xảy ra** (lần gần nhất thực sự lo lắng là khi nào, đã làm gì), không hỏi "bạn có dùng app như vậy không". Tính tới 2026-08-20 chưa có kết quả nghiên cứu người dùng nào được lưu trong repo — trùng với feedback FB-25 sau buổi review.

---
**Lưu ý cho AI:** Nếu một task được giao có vẻ đi ngược lại tầm nhìn hoặc phạm vi ở trên (đặc biệt các gạch đầu dòng "Out of scope" — ví dụ yêu cầu agent tự đổi liều thuốc), hãy **dừng lại và hỏi lại PM** thay vì tự suy diễn.
