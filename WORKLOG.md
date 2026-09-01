# Worklog — Team P-067 (VMEC-04 / CapyMedi)

> Lịch sử phát triển theo ngày, chứng minh team làm việc đều đặn.
>
> **Nguồn:** Tuần 1 ghi tay theo ngày trong quá trình làm việc, Tuần 2 theo `planning/sprints/sprint-02.md`. Từ 11/08 trở đi lấy trực tiếp từ `git log` trên GitHub.

**Phạm vi:** 2026-07-25 → 2026-09-01 · **494 commit** · **174 pull request đã merge** · **21 ngày có commit**

---

## Tuần 1: 25/07 – 01/08 — Đề tài, BRIEF & PRD


| Ngày | Thành viên | Công việc | Output | Giờ |
|---|---|---|---|---:|
| 25/07 (T7) | Cả team | Kickoff, thảo luận đề tài & pain point | Chốt hướng: AI nhắc thuốc & theo dõi tuân thủ | 2h |
| 25/07 | Cả team | Chốt phân chia vai trò | M.Đạt Lead/Data/AI · Yến PM/UI-UX/FE · T.Đạt AI/Fullstack/Tester · Trường Fullstack/Tech Lead | 1h |
| 26/07 (CN) | Trường | Thiết lập Git workflow (branch, PR, CI) | Quy tắc `feature/fix/chore`, PR review, CI ruff + pytest | 1.5h |
| 26/07 | Yến | Research app nhắc thuốc trên thị trường | Danh sách: Calendar thủ công, Max, Apple Health, MediSafe | 1.5h |
| 27/07 (T2) | Yến | So sánh tính năng các app | Bảng so sánh điểm mạnh/yếu | 2h |
| 27/07 | Trường | Trải nghiệm app Vinmec | Ghi nhận chưa có chatbot tương tự | 1.5h |
| 27/07 | T.Đạt, M.Đạt | Chuẩn bị case study chăm người thân dùng thuốc | Outline cho BRIEF | 1h |
| 28/07 (T3) | Yến | Kết luận research thị trường | **Chưa có sản phẩm nào ghép trọn vòng khép kín** đơn duyệt → nhắc → xác nhận có bằng chứng → escalate | 2h |
| 28/07 | Trường | Đối chiếu app Vinmec với đề tài | Input cho phần "điểm khác biệt" | 1.5h |
| 28/07 | T.Đạt, M.Đạt | Chia sẻ case study gia đình | Pain point bệnh nhân cao tuổi nhiều bệnh nền | 2h |
| 29/07 (T4) | Yến | Viết BRIEF phần 1–3 | Draft BRIEF | 2.5h |
| 29/07 | M.Đạt | BRIEF phần 4: điểm khác biệt AI | Xác nhận ảnh, hội thoại tự nhiên, đánh giá mức nghiêm trọng | 2h |
| 29/07 | T.Đạt, Trường | BRIEF phần 5: phạm vi MVP | Bảng cắt phạm vi | 1.5h |
| 30/07 (T5) | Yến | Hoàn thiện BRIEF | **BRIEF VMEC-04 hoàn chỉnh** | 2h |
| 30/07 | M.Đạt, T.Đạt | Bắt đầu PRD: tính năng theo vai trò | Draft bảng tính năng 4 vai trò | 2.5h |
| 30/07 | Trường | Yêu cầu phi chức năng | PRD phần 3 | 1.5h |
| 31/07 (T6) | M.Đạt, T.Đạt | PRD chi tiết: phác đồ, lịch nhắc, luồng phản hồi | PRD 2.1–2.5 | 3h |
| 31/07 | Yến | PRD: bỏ liều, safety layer, dashboard, người thân | PRD 2.6–2.10 | 2.5h |
| 31/07 | Trường | Ràng buộc an toàn + cắt phạm vi v1 | PRD 4–5 | 1.5h |
| 01/08 (T7) | Cả team | Review chéo BRIEF + PRD | ✅ **Gate 01 đạt** | 2h |
| 01/08 | Yến | Khởi tạo Figma wireframe | Board Figma (carry over) | 2h |
| 01/08 | Trường | Checklist Tuần 2 | Roadmap Tuần 2 | 1h |

**Tổng kết tuần:** Chốt Gate 01 — đề tài, BRIEF, PRD, vai trò và quy trình Git.

---

## Tuần 2: 02/08 – 08/08 — Dữ liệu thuốc, Vision & nền móng


| Task | Nội dung | Owner | Ưu tiên |
|---|---|---|---|
| TASK-001 | Thu thập & chuẩn hoá dữ liệu thuốc cho RAG | Nguyễn Minh Đạt | **P0** |
| TASK-002 | Khởi động tìm hiểu VLM đếm thuốc — chốt metric & cách đo cho bài toán đếm viên từ ảnh | Phạm Thành Đạt | **P0** |
| TASK-003 | Skeleton FastAPI + docker-compose (Postgres + pgvector) + CI xanh | Trương Quốc Trường | **P0** |
| TASK-008 | Bộ test set safety layer + redflag tiếng Việt | Phạm Thành Đạt | **P0** |
| TASK-004 | Form bác sĩ nhập đơn thuốc mô phỏng | Nguyễn Hải Yến | P1 |
| TASK-005 | Form khảo sát sức khoẻ hằng ngày | Nguyễn Hải Yến | P1 |
| TASK-006 | Chốt workflow hệ thống xuyên suốt | Cả team | P1 |
| TASK-009 | Hoàn thiện context base (`/specs`, `/adrs`, `/tasks`, `/planning`) | Cả team | P1 |
| TASK-010 | Build chatbot/RAG — backend + tích hợp frontend | Nguyễn Minh Đạt | **P0** |

**Tổng kết tuần:** Giải quyết rủi ro số 1 (dữ liệu thuốc có nguồn), khởi động hướng VLM đếm thuốc và thiết kế frontend cho cả 3 vai trò — đủ nền móng để tuần sau code feature được ngay.

---

## Tuần 3: 09/08 – 15/08 — Khởi tạo repo, auth thật & xác nhận ảnh

| Ngày | Commit | Ai (số commit) | Công việc chính |
|---|---:|---|---|
| 11/08 | 1 | M.Đạt 1 | Khởi tạo repo, cập nhật đường dẫn TASK-010 từ `src/` sang `backend/` |
| 12/08 | 14 | Trường 4 · M.Đạt 4 · Yến 3 · T.Đạt 3 | Auth-api thật (JWT) + login 3 vai trò · Nhận ảnh → đối chiếu → quyết định bước tiếp · Nối camera thật vào app · Gom thuốc thành đơn HITL |
| 13/08 | 20 | Trường 9 · Yến 7 · T.Đạt 3 · M.Đạt 1 | Luồng email đầy đủ (đăng ký/xác thực/reset/đổi mật khẩu + thu hồi token) · Bác sĩ tra cứu mọi bệnh nhân theo ID · **Gỡ trùng revision migration 0015/0016** · Sửa build vỡ do `useSearchParams` thiếu Suspense |
| 14/08 | 50 | M.Đạt 23 · Yến 15 · Trường 10 · T.Đạt 2 | Người thân theo dõi chéo bằng lời mời thật · Revamp trang bác sĩ (đơn thuốc, thông báo) · Chuẩn hoá ID bệnh nhân `BNxxxxx` · **Gỡ trùng revision 0020** · Dọn nợ ruff đang chặn CI |
| 15/08 | 0 | — | *(không có commit)* |

**Tổng kết tuần:** Repo lên GitHub, auth thật thay mock, luồng xác nhận ảnh chạy end-to-end. Trùng revision migration xuất hiện **2 lần** trong tuần.

---

## Tuần 4: 16/08 – 22/08 — Canonical V2, đổi nền auth & rebrand

| Ngày | Commit | Ai (số commit) | Công việc chính |
|---|---:|---|---|
| 16/08 | 8 | M.Đạt 7 · Trường 1 | **Dựng lại dữ liệu thuốc thành Canonical V2 có provenance** (TASK-001) · Nối agent vào nền dữ liệu V2 |
| 17/08 | 21 | M.Đạt 15 · Trường 6 | Tích hợp Better Auth cho Google login · Chuẩn hoá "1 email = 1 tài khoản" không phân biệt hoa/thường · Giới hạn đăng ký chỉ role `patient` · Gỡ trùng migration 0025 · Sửa CI lint |
| 18/08 | 8 | M.Đạt 5 · T.Đạt 2 · Trường 1 | Nén ảnh liều + dọn ảnh hết hạn |
| 19/08 | 52 | Trường 29 · T.Đạt 13 · M.Đạt 5 · Yến 5 | **Rebrand toàn bộ portal bệnh nhân sang CapyMedi** · Admin dashboard quản lý tài khoản · Admin-RAG tra cứu dữ liệu thuốc · Tự khai đã uống (không ảnh) kèm người thân duyệt |
| 20/08 | 9 | T.Đạt 5 · M.Đạt 4 | Nhắc uống thuốc leo thang 3 mức · Nhắc nhở từ người thân + cảnh báo hồ sơ sức khoẻ · Hướng dẫn chụp ảnh tại chỗ |
| 21/08 | 36 | Trường 13 · Yến 13 · M.Đạt 10 | **Chặn alembic rollback im lặng, bỏ auto-stamp không an toàn** · Viết `safe_migrate.py` phục hồi revision mồ côi · Chạy `alembic upgrade head` lúc container khởi động · RAG monitoring dashboard · Dockerfile multi-stage · Chỉ cho kê thuốc trong danh mục (FB-14) |
| 22/08 | 67 | M.Đạt 48 · T.Đạt 11 · Trường 4 · Yến 4 | **Kiến trúc Agent V2** + conversation state có cấu trúc · Hệ thống yêu cầu bổ sung thuốc · Module quản lý thuốc cho admin (CRUD) · **Gỡ trùng revision 0038 và 0041** |

**Tổng kết tuần:** Tuần nặng nhất về hạ tầng — đổi nền dữ liệu thuốc, đổi nền auth, và xử lý dứt điểm nhóm lỗi migration/deploy. 67 commit ngày 22/08 là ngày cao nhất dự án.

---

## Tuần 5: 23/08 – 29/08 — Agent V2, quan sát được & đánh giá tự động

| Ngày | Commit | Ai (số commit) | Công việc chính |
|---|---:|---|---|
| 23/08 | 32 | M.Đạt 17 · Yến 10 · T.Đạt 4 · Trường 1 | **BUILD-29F** triage y tế + định tuyến an toàn liều · **BUILD-32** observability & lưu trace · Hộp cảnh báo có bộ lọc · Nhật ký thao tác bác sĩ · Trang Tổng quan đọc số liệu thật, bỏ hết mock |
| 24/08 | 6 | Trường 4 · Yến 2 | Endpoint auth cho đăng ký + Google OAuth · Đưa mọi số liệu trang Tổng quan về chung một kỳ |
| 25/08 | 26 | M.Đạt 25 · T.Đạt 1 | **BUILD-33** LLM Judge production · **BUILD-34** Safety & Handoff monitoring · **BUILD-35** Golden Set & đánh giá liên tục · **BUILD-36** Admin Monitoring V2 · **BUILD-37 tìm ra bug thật `content_available` sai khoá** · **BUILD-38** Quality Improvement Loop |
| 26/08 | 39 | M.Đạt 35 · T.Đạt 2 · Trường 2 | **BUILD-40** Router Quality Loop · **BUILD-42** Answerability Gate & chuyển bác sĩ · **BUILD-43** Conversation State · **BUILD-44** hàng đợi chat bác sĩ & takeover · Hệ thống điểm thưởng & rank · **Gỡ trùng migration 0053** |
| 27/08 | 41 | M.Đạt 34 · Trường 6 · T.Đạt 1 | Nhận diện ảnh thuốc trong chat (B-07) · Giới hạn upload & dọn dẹp · Admin dashboard đọc metric thật, bỏ mock · Bật/tắt chụp ảnh trong Cài đặt |
| 28/08 | 36 | M.Đạt 18 · Trường 10 · Yến 5 · T.Đạt 3 | **B-08** bật nhận diện ảnh thuốc production + sửa cold-start · Làm cứng OCR (union color+grayscale, partial-token có đối chứng) · **Nhắc thuốc qua Telegram** · **Voice STT/TTS** cho trợ lý · Điểm thưởng theo cách xác nhận liều · Workspace tư vấn bác sĩ |
| 29/08 | 13 | Trường 11 · T.Đạt 2 | Dashboard giám sát agent: 6 KPI failure-mode, time series, phân bố Judge · Việt hoá KPI · **BUILD-47/48/49 giữ ngữ cảnh hội thoại qua các lượt follow-up** |

**Tổng kết tuần:** Trọng tâm chuyển từ "làm tính năng" sang "đo được và tự đánh giá được". Chuỗi BUILD-32 → BUILD-49 dựng xong vòng quan sát–đánh giá–cải thiện.

---

## Tuần 6: 30/08 – 01/09 — Đồng bộ hội thoại, runtime V3 & thống kê tuân thủ

| Ngày | Commit | Ai (số commit) | Công việc chính |
|---|---:|---|---|
| 30/08 | 3 | M.Đạt 3 | TASK-021 đồng bộ hội thoại bác sĩ ↔ bệnh nhân |
| 31/08 | 8 | Trường 6 · M.Đạt 2 | **Runtime profile V3 fail-closed** · Admin dashboard duyệt/từ chối yêu cầu bổ sung thuốc · Trang sức khoẻ bệnh nhân + routing sub-resource |
| 01/09 | 4 | T.Đạt 4 | **Chốt liều quá hạn, gán đúng nhãn `DELAYED`, bỏ N+1 ảnh** · Sửa mẫu số tuân thủ, thu gọn nhật ký, dùng `has_photo` · TASK-022 · Chuyển ranh giới giao dịch về người gọi |

**Tổng kết tuần:** Sửa lỗi thống kê tuân thủ — tỉ lệ hiển thị của một bệnh nhân từ **88% (sai)** về **25% (đúng)**, và loại bỏ 147 request thừa mỗi lần mở trang Lịch sử.

---

## Nhịp làm việc

| Chỉ số | Giá trị |
|---|---|
| Ngày có commit | 21 / 22 ngày kể từ khi khởi tạo repo |
| Ngày cao nhất | 22/08 — 67 commit |
| Trung bình ngày làm việc | ~23,5 commit |
| Pull request đã merge | 174 |
| Ngày nghỉ trong kỳ | 15/08 |

Team commit **đều đặn hằng ngày** suốt từ 11/08 đến 01/09, chỉ nghỉ đúng một ngày (15/08) — không dồn commit vào cuối kỳ.

---

## Cách tái tạo bảng này

```bash
# Commit theo ngày
git log --format="%ad" --date=short | sort | uniq -c

# Đóng góp theo người (gộp đúng khi đã có .mailmap)
git shortlog -sne --all

# Chi tiết một ngày
git log --format="%ad|%an|%s" --date=short --since=2026-08-22 --until=2026-08-23
```
