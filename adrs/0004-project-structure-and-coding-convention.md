# ADR-0004: Project Structure & Coding Convention

**Status:** Accepted
**Ngày:** 2026-08-04
**Người đề xuất:** Nguyễn Minh Đạt (Architect)
**Người duyệt:** Trương Quốc Trường (Tech Leader) — `[chờ xác nhận đầu Sprint 02]`

## Bối cảnh (Context)

Khi AI code lặp đi lặp lại nhiều lần bởi nhiều người khác nhau gọi, nếu không có convention thống nhất, mỗi lần AI sẽ "tự sáng tạo" một phong cách khác nhau — code trở nên hỗn loạn, khó review, khó maintain. Với VMEC-04, 4 người + AI cùng làm trên một monolith trong 5 tuần, rủi ro này rất cao.

## Quyết định (Decision)

Thống nhất cấu trúc dự án, quy ước code và kỹ thuật cho toàn bộ codebase.

### 1. Cấu trúc thư mục

```
├── src/
│   ├── agents/              # LangGraph
│   │   ├── graph.py         # Main graph (nodes + edges)
│   │   ├── state.py         # State schema
│   │   ├── nodes/           # parse_phac_do, sinh_lich_nhac, phan_loai_hoi_thoai,
│   │   │                    # doi_chieu_anh, danh_gia_muc_nghiem_trong, escalate, hitl_duyet_lich
│   │   └── tools/           # rag.py (pgvector), vision.py, notification.py
│   ├── api/                 # FastAPI routes, chia theo role
│   │   ├── doctor/
│   │   ├── patient/
│   │   ├── caregiver/
│   │   └── deps.py          # dependency: auth, phân quyền, session DB
│   ├── models/              # Pydantic schema (DTO) + SQLAlchemy model
│   ├── services/            # Business logic theo domain
│   │   ├── prescription/  scheduling/  safety/  escalation/  reporting/  audit/
│   ├── config.py            # Settings (pydantic-settings, đọc từ .env)
│   └── main.py              # App entry point
├── tests/                   # pytest — mirror cấu trúc src/
├── eval/                    # Script + kết quả đánh giá AI (accuracy, recall)
├── data pharmacy/           # Dữ liệu thuốc cho RAG (theo schema.json)
├── docs/  specs/  adrs/  tasks/  planning/
└── .github/workflows/       # CI: ruff + pytest
```

**Quy tắc thư mục:**
- Một domain = một thư mục con trong `src/services/`. Không tạo file `utils.py` khổng lồ dùng chung mọi nơi.
- `src/api/` **chỉ** làm việc HTTP: validate input, gọi service, map lỗi. **Không** chứa business logic.
- `src/services/` **không** import `fastapi` (trừ `HTTPException` nếu thật cần) — để logic test được mà không cần dựng app.
- `tests/` mirror cấu trúc `src/`: `src/services/scheduling/` → `tests/services/test_scheduling.py`.

### 2. Naming convention

| Đối tượng | Quy ước | Ví dụ |
|---|---|---|
| File / module Python | `snake_case.py` | `dose_scheduler.py` |
| Class | `PascalCase` | `DoseEvent`, `SafetyClassifier` |
| Hàm / biến | `snake_case` | `sinh_lich_nhac()`, `dose_window_minutes` |
| Hằng số | `UPPER_SNAKE_CASE` | `DOSE_WINDOW_MINUTES = 30` |
| Bảng DB | `snake_case`, số ít | `dose_event`, `prescription`, `audit_log` |
| API path | `kebab-case`, danh từ số nhiều | `/api/v1/photo-verifications` |
| Field JSON API | `snake_case` | `window_start`, `detected_count` |
| Enum value | `UPPER_SNAKE_CASE` | `TAKEN`, `AWAITING_CAREGIVER` |
| Branch Git | `feature/<TASK-ID>-<mo-ta-ngan>` | `feature/TASK-003-dose-scheduler` |

**Tên nghiệp vụ:** dùng đúng tên trong [`../specs/glossary.md`](../specs/glossary.md) cột "Tên trong code". Node LangGraph giữ tên tiếng Việt không dấu đã chốt (`parse_phac_do`, `phan_loai_hoi_thoai`…); khái niệm kỹ thuật phổ thông dùng tiếng Anh (`dose_event`, `severity`). **Không** tồn tại song song hai tên cho cùng một thứ.

### 3. Code style (lint, format)

- **Python 3.11+**, formatter & linter: **`ruff`** (đã dùng trong CI từ 2026-07-26).
- Line length: **100**.
- **Type hint bắt buộc** cho mọi hàm public trong `src/services/` và `src/agents/`.
- Docstring: bắt buộc cho module và hàm public; viết **tiếng Việt** cho logic nghiệp vụ (giải thích *vì sao*), tiếng Anh cho phần kỹ thuật thuần.
- Không commit code bị comment-out; không để `print()` trong `src/` (dùng logger).

### 4. Error handling

- Định nghĩa exception nghiệp vụ riêng trong `src/services/<domain>/errors.py`, kế thừa từ một base chung (VD: `VmecError`).
- Tầng `src/api/` bắt exception nghiệp vụ và map sang HTTP code + body theo đúng [`../specs/api-contracts.md`](../specs/api-contracts.md) §10.
- **Không bao giờ trả stack trace / chi tiết nội bộ cho FE** (500 chỉ trả message chung).
- **Không dùng `except: pass`.** Nuốt lỗi âm thầm trong dự án y tế là không chấp nhận được.
- Lỗi LLM/Vision (timeout, rate limit) phải có fallback rõ ràng — đặc biệt: **LLM lỗi thì safety layer vẫn phải chạy keyword layer** (BR-6.3).

### 5. Logging

- Dùng `logging` chuẩn của Python, cấu hình tập trung ở `src/config.py`; **log dạng JSON** để dễ truy vết.
- Mức: `DEBUG` (local) · `INFO` (mốc nghiệp vụ: đã gửi nhắc, đã đóng dose window) · `WARNING` (fallback được kích hoạt) · `ERROR` (thất bại cần người xem).
- Mọi log liên quan tới một liều phải kèm `dose_id` và `patient_id` để truy vết.
- **Không log PHI/PII dạng plain** (ảnh thuốc, nội dung hội thoại đầy đủ, thông tin định danh bệnh nhân). Log `patient_id`, không log tên/địa chỉ.
- `audit_log` (bảng DB) **khác** logging kỹ thuật — audit là bản ghi nghiệp vụ append-only cho bác sĩ xem, xem [`../specs/business-rules.md`](../specs/business-rules.md) BR-7.5.

### 6. Validation

- Mọi input từ ngoài vào validate bằng **Pydantic model**, không tự viết `if` kiểm tra tay ở route.
- Ràng buộc nghiệp vụ (VD: "chỉ sinh lịch từ phác đồ `approved`") kiểm tra ở tầng `services/`, trả lỗi 422 theo contract — **không** phó mặc cho DB constraint báo lỗi.
- Phân quyền kiểm tra **cả role lẫn quan hệ liên kết** với bệnh nhân (xem [`../specs/user-roles.md`](../specs/user-roles.md)); role đúng nhưng không liên kết → 403.

### 7. Testing style

Chi tiết ở [ADR-0001](./0001-test-strategy.md). Tóm tắt:
- `pytest`, đặt tên `test_<hành vi được kiểm chứng>` — mô tả hành vi, không mô tả tên hàm.
- **Mock LLM/Vision trong `pytest`** — không gọi API thật; gọi thật chỉ trong `eval/`.
- Logic nghiệp vụ tất định → unit test bắt buộc. Đầu ra LLM/Vision → đo bằng ngưỡng chỉ số trên test set.

### 8. Config & secrets

- Mọi config qua biến môi trường, đọc bằng `pydantic-settings` trong `src/config.py`. **Không hardcode** URL/khoá/ngưỡng trong code.
- Mọi con số nghiệp vụ (`DOSE_WINDOW_MINUTES`, ngưỡng confidence, SLA) khai báo thành **hằng số có tên**, giá trị lấy từ [`../specs/business-rules.md`](../specs/business-rules.md).
- **Không commit `.env`** — chỉ commit `.env.example`. Không commit dữ liệu bệnh nhân thật, ảnh thuốc thật, hay `.ai-log/*.jsonl`.

### 9. Commit convention

Theo `AGENTS.md` §5: `<TASK-ID>: <mô tả ngắn gọn, dạng động từ>`

```
TASK-003: them cron job quet dose_event moi phut
TASK-008: bo sung 12 tu khoa redflag cho safety layer
```

Commit nhỏ, mỗi commit một ý. Không squash làm mất ngữ cảnh quan trọng.

### 10. Prompt & phiên bản model (đặc thù dự án AI)

- Prompt **không viết inline giữa code logic** — đặt trong module/file prompt riêng của từng node để review và version được.
- Mỗi prompt có định danh + phiên bản; ghi vào `audit_log` cùng tên model đã dùng, để truy vết "vì sao hôm đó agent trả lời như vậy".
- Đổi prompt/model → **chạy lại bộ đánh giá trong `eval/`** trước khi merge; không đổi prompt "cho cảm giác tốt hơn" mà không đo.

## Vì sao thân thiện với AI + Team

- Agent không tự sáng tạo mỗi lần một kiểu.
- Code sinh ra đồng nhất hơn giữa các lần chạy, giữa các thành viên.
- Review, bảo trì, refactor dễ dàng hơn vì code có cùng "ngôn ngữ".
- Ranh giới `api/` ↔ `services/` rõ ràng giúp AI biết đặt code mới vào đâu mà không phải hỏi.

## Hệ quả (Consequences)

**Tích cực:**
- Codebase nhất quán, dễ đọc, dễ maintain lâu dài.
- Business logic tách khỏi HTTP → test được nhanh, không cần dựng app.
- Ràng buộc về log/secret giảm rủi ro lộ dữ liệu y tế.

**Đánh đổi / rủi ro:**
- Cần enforce bằng công cụ (`ruff` trong CI) chứ không chỉ dựa vào tự giác, nếu không convention sẽ bị trôi dần theo thời gian.
- Tách `api/` ↔ `services/` khiến task nhỏ phải sửa 2 file thay vì 1 — chấp nhận đổi lấy khả năng test.
- Một số quy ước ở đây (VD: JSON logging, prompt versioning) chưa có code để kiểm chứng — cần rà lại sau Sprint 02 khi codebase đã hình thành.

## Câu chốt

> Không có convention, AI sẽ tạo ra code hỗn loạn rất nhanh.
