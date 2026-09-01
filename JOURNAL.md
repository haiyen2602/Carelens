# Development Journal — Team P-067 (VMEC-04 / CapyMedi)

> Nhật ký phát triển: quyết định kỹ thuật và lý do, khó khăn gặp phải và cách giải quyết, bài học rút ra.
>
> **Nguồn dữ liệu:** Tuần 1–2 lấy từ `WORKLOG.md` và `planning/sprints/`. Từ Tuần 3 trở đi lấy từ lịch sử commit thật trên GitHub.
>
> **Quy mô tính tới 2026-09-01:** 494 commit · 174 pull request đã merge · 4 thành viên · 14 ADR.
>
> *(`git log` thô hiện 6 danh tính nhưng chỉ có 4 người — hai thành viên dùng hai tài khoản git trùng email. Xem `WORKLOG.md` để biết ánh xạ.)*

---

## Week 1: 25/07 – 01/08 — Đề tài, BRIEF & PRD

### Mục tiêu tuần này
- [x] Chọn đề tài, xác định vấn đề và người dùng chính
- [x] Research thị trường: app tương tự, app Vinmec, case study chăm sóc người thân
- [x] Viết BRIEF và PRD hoàn chỉnh
- [x] Chốt phân chia vai trò và thiết lập Git workflow

### Đã hoàn thành
- Research các app nhắc thuốc đã có trên thị trường (Calendar thủ công, app Max, Apple Health, MediSafe) và trải nghiệm app Vinmec để đối chiếu.
- Chia sẻ câu chuyện thực tế chăm sóc người thân lớn tuổi dùng thuốc — làm cơ sở xác định pain point thay vì suy đoán.
- Hoàn thành BRIEF và PRD: 10 tính năng theo vai trò (bác sĩ / bệnh nhân / người thân / agent), yêu cầu phi chức năng, ràng buộc an toàn, cắt phạm vi v1.
- Chốt vai trò: M.Đạt (Team Lead/Data/AI) · Yến (PM/UI-UX/FE) · T.Đạt (AI/Fullstack/Tester) · Trường (Fullstack/Tech Lead).
- Thiết lập Git workflow: nhánh `feature/fix/chore`, PR bắt buộc review, CI `ruff` + `pytest` trên mọi push.

### Quyết định kỹ thuật & lý do
| Quyết định | Lý do |
|---|---|
| Bắt buộc Human-in-the-loop: bác sĩ duyệt mọi thay đổi phác đồ (ADR-0010) | Không có điều này thì bác sĩ sẽ không tin dùng — đây là điều kiện tiên quyết, không phải tính năng phụ |
| Agent **không được** kê đơn/đổi thuốc, cắt khỏi phạm vi v1 | Ranh giới an toàn y tế; ghi thẳng vào PRD để không bị trôi phạm vi về sau |
| Không tích hợp EMR/HIS thật trong 5 tuần | Phạm vi bất khả thi với thời gian có; ghi rõ trong bảng cắt phạm vi |

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| Chưa có bộ dữ liệu thuốc thực tế để làm RAG | Tìm nguồn có sẵn, nếu không đủ thì tự crawl | Chuyển thành ưu tiên P0 của Sprint 02 |
| Rủi ro cao nhất: dữ liệu thiếu → agent "bịa" thông tin thuốc | Xác định RAG trên dữ liệu **có nguồn** là ưu tiên kỹ thuật số 1, ghi thành giả định rủi ro trong BRIEF | Định hình toàn bộ hướng kỹ thuật của Sprint 02 |
| Dễ lan man tính năng trong 5 tuần | Bảng cắt phạm vi MVP / sprint sau / không làm trong PRD | Dùng làm kim chỉ nam cho các tuần tiếp theo |

### Bài học
- Điểm mấu chốt của đề tài **không phải** "bệnh nhân quên thuốc" mà là **"bác sĩ ra quyết định lâm sàng trên dữ liệu sai"**. Giữ thông điệp này xuyên suốt khi trình bày.
- Chấp nhận đánh đổi "báo thừa còn hơn bỏ sót" cho recall triệu chứng nghiêm trọng — đây là chỉ số quan trọng nhất của cả hệ thống.

---

## Week 2: 02/08 – 08/08 — Dữ liệu thuốc, Vision & nền móng kỹ thuật


### Mục tiêu tuần này
- [x] Giải quyết rủi ro số 1: có dữ liệu thuốc thật, **có nguồn**, nằm trong repo (TASK-001)
- [x] Khởi động tìm hiểu VLM đếm thuốc: chốt metric và cách đo cho bài toán đếm viên từ ảnh (TASK-002)
- [x] Thiết kế frontend: wireframe & UI flow trên Figma cho 3 vai trò bác sĩ / bệnh nhân / người thân (TASK-007)
- [x] Dựng skeleton FastAPI + docker-compose (Postgres + pgvector) + CI xanh (TASK-003)
- [x] Hoàn thiện context base: `/specs`, `/adrs`, `/tasks`, `/planning` (TASK-009)
- [x] Bộ test set safety layer + danh sách redflag tiếng Việt (TASK-008)

### Quyết định kỹ thuật & lý do
| Quyết định | Lý do |
|---|---|
| **pgvector** thay vì vector store riêng (ADR-0008) | Đã có Postgres cho dữ liệu nghiệp vụ; thêm một hệ thống nữa là thêm một thứ phải vận hành và đồng bộ |
| **Safety layer 2 tầng: keyword OR LLM** (ADR-0009) | Keyword bắt nhanh và chắc các redflag đã biết; LLM bắt các cách diễn đạt lạ. `OR` để giảm bỏ sót, chấp nhận báo thừa |
| **API contract-first** (ADR-0003) | Frontend và backend làm song song bởi hai người khác nhau — chốt hợp đồng trước để không phải sửa chéo |
| Ảnh xác nhận có **đường thoát** khi không đối chiếu được (ADR-0011) | Có thuốc không kiểm chứng được bằng ảnh (thuốc tiêm); ép bệnh nhân chụp lại là vô nghĩa |

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| Không có sẵn bộ dữ liệu thuốc tiếng Việt đủ dùng | Tự viết crawler (`crawler/`) lấy dữ liệu nhà thuốc, chuẩn hoá theo `schema.json`, giữ nguồn cho từng bản ghi | Có dữ liệu thật trong repo — gỡ được rủi ro số 1 |
| Chưa biết đo bài toán đếm viên thuốc thế nào cho đúng | Làm spike riêng (TASK-002) để chốt metric trước khi code | Tránh được việc code xong mới phát hiện không đo được |
| Thiết kế frontend cho 3 vai trò rất khác nhau (bác sĩ dùng web, bệnh nhân cao tuổi dùng điện thoại) | Tách wireframe theo từng vai trò trên Figma thay vì dùng chung một bộ màn hình | Giao diện bệnh nhân được tối ưu riêng cho chữ to, thao tác ít bước |

### Bài học
- Tách "spike đo lường" ra khỏi "code tính năng" giúp không mắc kẹt vào một hướng kỹ thuật sai — chốt được metric cho bài toán đếm viên trước khi viết dòng code nhận diện nào.
- Thiết kế giao diện cho người cao tuổi là ràng buộc kỹ thuật, không phải việc trang trí: nó quyết định số bước thao tác và cách trình bày thông tin ngay từ khâu wireframe.

---

## Week 3: 09/08 – 15/08 — Khởi tạo repo, auth thật & luồng xác nhận ảnh

### Mục tiêu tuần này
- [x] Khởi tạo repo, đưa toàn bộ nền móng lên GitHub
- [x] Auth thật bằng JWT cho 3 vai trò (bác sĩ / bệnh nhân / admin)
- [x] Luồng xác nhận liều bằng ảnh chạy end-to-end với camera thật
- [x] Luồng bác sĩ duyệt đơn thuốc (HITL) + người thân theo dõi

### Đã hoàn thành
- `feat(auth)`: xây auth-api thật (JWT), wire login cho cả 3 vai trò; sau đó bổ sung đăng ký / xác thực email / đặt lại & đổi mật khẩu kèm thu hồi token.
- `feat(photo-verification)`: nhận ảnh → đối chiếu → quyết định bước tiếp theo, và nối camera thật vào app bệnh nhân.
- `feat(prescription)`: gom thuốc thành đơn HITL, chu kỳ liều, tra cứu bệnh nhân theo ID; nối luồng bác sĩ duyệt phác đồ.
- `feat(caregiver)`: bệnh nhân mời nhau theo dõi chéo bằng lời mời thật, bỏ toàn bộ mock.
- Chuyển dữ liệu bác sĩ/bệnh nhân/người thân sang backend thật, gỡ hết prototype mock.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| **Trùng số revision migration** khi nhiều người cùng thêm migration (0015/0016, rồi 0020) | Đánh số lại thủ công và merge chuỗi revision | Giải quyết được nhưng **tái diễn 3 lần** — dấu hiệu quy trình chưa ổn |
| Frontend build vỡ vì `useSearchParams()` không bọc trong `Suspense` | Bọc các trang liên quan trong `Suspense` boundary | Build thông trở lại |
| Đổi sang JWT thật làm các trang bác sĩ trả 401 | Sửa proxy frontend forward đúng bearer token | Hết lỗi 401 |
| `PATCH /patients/{id}` làm app chết ngay lúc khởi động (undefined name) | Sửa lỗi và bổ sung test cho endpoint | App khởi động ổn định |

### Bài học
- **Trùng revision migration là lỗi hệ thống, không phải lỗi cá nhân.** Ba lần trong một tuần nghĩa là quy trình đang thiếu một bước kiểm tra tự động, không phải do ai đó bất cẩn.
- Lỗi làm app **chết lúc khởi động** nguy hiểm hơn hẳn lỗi runtime thông thường: nó không lộ ra khi review code mà chỉ lộ khi deploy.

---

## Week 4: 16/08 – 22/08 — Canonical V2, đổi nền auth & rebrand CapyMedi

### Mục tiêu tuần này
- [x] Dựng lại dữ liệu thuốc thành **Canonical V2 có provenance** (TASK-001)
- [x] Đưa agent chạy trên nền dữ liệu V2
- [x] Rebrand toàn bộ giao diện bệnh nhân sang CapyMedi
- [x] Dựng admin dashboard + RAG monitoring
- [x] Dockerfile multi-stage cho production

### Quyết định kỹ thuật & lý do
| Quyết định | Lý do |
|---|---|
| **Canonical V2 kèm provenance cho từng bản ghi** (ADR-0012) | Agent phải trích được nguồn; không có provenance thì không thể chứng minh câu trả lời không phải bịa |
| **Chuyển auth từ Better Auth sang Supabase** (ADR-0013) | Better Auth phát sinh nhiều ca lỗi ghép tài khoản Google; đổi nền sớm rẻ hơn vá tiếp |
| **Danh mục thuốc là allowlist động** (ADR-0013, FB-14) | Chỉ cho kê thuốc có trong danh mục để agent không sinh ra thuốc không tồn tại; kèm "đường thoát" cho bác sĩ yêu cầu bổ sung |
| Chạy `alembic upgrade head` lúc container khởi động | Deploy không cần bước thủ công, giảm sai sót giữa các môi trường |

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| **Alembic rollback im lặng** — migration báo thành công nhưng không áp dụng gì | Chặn rollback im lặng, bỏ auto-stamp không an toàn, viết `scripts/safe_migrate.py` có kiểm tra tính nhất quán schema và phục hồi revision mồ côi | Đây là bug nguy hiểm nhất tuần: nó *im lặng*, không có triệu chứng cho tới khi dữ liệu sai |
| Cột `supabase_uid` không được thêm ở một số môi trường | Kiểm tra và tạo cột ngay lúc FastAPI khởi động, ngoài đường alembic | Môi trường lệch schema tự phục hồi |
| Người dùng thử báo chỉ số cơ thể phi thực tế lọt qua (FB-08, FB-09) | Chặn giá trị phi thực tế ở cả frontend lẫn backend | Sửa theo feedback thật, không phải giả định |
| Xưng hô của AI với bệnh nhân không phù hợp (cháu/bác) | Đổi sang tôi/bạn | Nhỏ nhưng ảnh hưởng trực tiếp trải nghiệm người cao tuổi |

### Bài học
- **Lỗi im lặng đắt hơn lỗi ồn ào.** Alembic rollback im lặng không làm gì đổ vỡ ngay — nó chỉ để lại schema sai và bung ra ở nơi khác. Từ đó nhóm ưu tiên fail-closed thay vì fail-silent.
- Đổi nền tảng auth giữa dự án rất tốn, nhưng **đổi muộn còn tốn hơn**. Quyết định sớm ở tuần 4 rẻ hơn nhiều so với tuần 6.

---

## Week 5: 23/08 – 29/08 — Agent V2, quan sát được & đánh giá tự động

### Mục tiêu tuần này
- [x] Agent V2: phân loại triage y tế + định tuyến an toàn liều (BUILD-29F)
- [x] Observability bền vững + lưu trace (BUILD-32)
- [x] LLM Judge production + Golden Set + vòng cải thiện chất lượng (BUILD-33/35/38/40)
- [x] Answerability Gate & chuyển bác sĩ (BUILD-42), Conversation State (BUILD-43)
- [x] Hệ thống điểm thưởng & rank cho bệnh nhân
- [x] Nhận diện ảnh thuốc trong chat (B-07/B-08), nhắc thuốc qua Telegram, voice STT/TTS

### Quyết định kỹ thuật & lý do
| Quyết định | Lý do |
|---|---|
| **Answerability Gate**: agent tự nhận "không đủ căn cứ" và chuyển bác sĩ | Thà từ chối còn hơn trả lời sai trong ngữ cảnh y tế |
| **LLM Judge + Golden Set chạy liên tục** | Không có số đo thì không biết sửa prompt làm tốt lên hay tệ đi |
| **Warm OCR catalog index lúc khởi động** | Đo được: request đầu tiên timeout, từ request 2 chỉ ~0.3s. Không warm thì người dùng thật đầu tiên sau mỗi lần restart phải "bốc thăm" chịu độ trễ |
| Nhận diện ảnh thuốc chỉ tự động ở nhóm đủ confidence | Đo trên golden set 25 ảnh: mức `cao` đúng 9/9, mức `thấp` đúng 0/11 — độ tin cậy tự chấm dự báo được độ đúng |

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| BUILD-37 phát hiện **sai khoá `content_available`** — dashboard hiển thị N/A hàng loạt | Sửa khoá và bổ sung test | Bug thật, tìm ra nhờ chính vòng đánh giá tự động vừa dựng |
| Lại **trùng revision migration 0053** giữa hai nhánh làm song song | Đánh số lại, merge chuỗi | Lần thứ 4 — xác nhận cần công cụ tự động chứ không thể trông vào kỷ luật |
| Nhiều BUILD phải sửa 1–2 vòng sau review (BUILD-33/34/35/36/38/42/43/44) | Chấp nhận vòng review chặt, ghi lại phản hồi trong báo cáo BUILD | Chất lượng tăng, đổi lại tốc độ chậm hơn |

### Bài học
- **Dựng hệ thống đánh giá tự động sớm thì chính nó tìm ra bug cho mình.** BUILD-37 tìm ra lỗi khoá dữ liệu mà không ai để ý bằng mắt thường.
- Độ tin cậy do model tự chấm **có giá trị thật** nếu chịu đo: nó cho phép biến một mô hình chính xác 48% thành một luồng dùng được, bằng cách chỉ tự động hoá phần model tự tin.

---

## Week 6: 30/08 – 01/09 — Đồng bộ hội thoại, runtime V3 & sửa thống kê tuân thủ

### Mục tiêu tuần này
- [x] Đồng bộ hội thoại bác sĩ ↔ bệnh nhân (TASK-021)
- [x] Runtime profile V3 fail-closed
- [x] Dashboard giám sát admin theo thời gian thực
- [x] Sửa lỗi thống kê tuân thủ và vòng đời liều thuốc (TASK-022)

### Quyết định kỹ thuật & lý do
| Quyết định | Lý do |
|---|---|
| **Runtime profile V3 fail-closed** | Khi cấu hình thiếu thì dừng hẳn thay vì chạy tiếp ở trạng thái không xác định — rút ra trực tiếp từ bài học "lỗi im lặng" tuần 4 |
| Chốt liều quá hạn theo mốc **"qua ngày mới giờ VN"**, không phải hết cửa sổ ±30 phút | Liều 20:00 mà 20:45 mới xác nhận là *uống muộn*, không phải *bỏ liều*. Chốt sớm sẽ cướp mất cơ hội xác nhận muộn |
| Liều xác nhận muộn được **50% điểm** thay vì 0 | Ở mức 0, bệnh nhân không còn lý do xác nhận muộn và sẽ bỏ luôn — mất cả tín hiệu tuân thủ lẫn liều thuốc |
| `AWAITING_CAREGIVER` không bao giờ tự chuyển thành bỏ liều | Lỗi ở người thân chưa duyệt, không phải bệnh nhân bỏ thuốc — phạt nhầm người |

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|---|---|---|
| **Không có gì chuyển `PENDING` → `MISSED`.** Đo trên DB thật: 122/142 liều đã quá hạn nằm im vĩnh viễn | Thêm job chốt liều quá hạn + script backfill có báo cáo audit, không bắn cảnh báo cho liều cũ | Tỉ lệ tuân thủ hiển thị của một bệnh nhân từ **88% (sai)** về **25% (đúng)** |
| Trang Lịch sử bắn **147 request HTTP mỗi lần mở** để hỏi từng liều có ảnh hay không | Thêm `has_photo` vào `GET /doses` bằng một `LEFT JOIN` | 147 request → 0 request thừa |
| Backend gán thẳng `body.status` client gửi lên nên không bao giờ sinh ra nhãn `DELAYED` | Backend tự đối chiếu `window_end` để quyết định nhãn | Chỉ số "xác nhận muộn" hết vô nghĩa (trước đó luôn bằng 0) |

### Bài học
- **Con số hiển thị sai nguy hiểm hơn không hiển thị gì.** 88% tuân thủ trên một bệnh nhân thực tế chỉ đạt 25% có thể khiến bác sĩ kết luận sai — đúng cái rủi ro mà cả dự án sinh ra để phòng.
- Khi loại một trạng thái ra khỏi *cả tử số lẫn mẫu số*, hệ thống vô tình **thưởng cho sự im lặng**: bệnh nhân không làm gì thì biến mất khỏi phép tính.
- Ba lỗi trong tuần này đều đã nằm sẵn trong comment của code từ nhiều tuần trước. **Ghi lại nợ kỹ thuật là tốt, nhưng ghi rồi để đó thì nó vẫn bung.**

---

## Tổng kết xuyên suốt dự án

### Ba bài học lớn nhất
1. **Ưu tiên rủi ro trước tính năng.** Rủi ro số 1 (dữ liệu thuốc thiếu → agent bịa) được nhận diện ngay Tuần 1 và giải quyết ở Tuần 2, trước khi viết bất kỳ tính năng nào phụ thuộc vào nó.
2. **Fail-closed thay vì fail-silent.** Bài học từ vụ alembic rollback im lặng (Tuần 4) 
3. **Không đo thì không biết mình đang tốt lên hay tệ đi.** Golden set và LLM Judge dựng ở Tuần 5 lập tức tìm ra bug thật, và cho phép quyết định dựa trên số chứ không dựa vào cảm giác.

### Nếu được làm lại
- **Tự động hoá kiểm tra trùng revision migration ngay từ đầu.** Lỗi này tái diễn 4 lần và lần nào cũng tốn thời gian gỡ; cùng loại với việc `adrs/` hiện có hai file cùng số `0013`.
- **Dọn dữ liệu lớn khỏi repo sớm hơn.** Thư mục dữ liệu thuốc chiếm 86% số file trong repo, phát hiện quá muộn để xử lý triệt để trước hạn nộp.
