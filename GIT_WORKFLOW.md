# Git Workflow — Team P-067

> Quy tắc chung khi push/merge lên repo chung. Đọc trước khi code, tránh conflict và ghi đè code nhau.

---

## Vai trò

| Vai trò | Người phụ trách | Trách nhiệm |
|---|---|---|
| **Tech Lead / Merge chính** | Trương Quốc Trường | Review & merge Pull Request vào `main`, xử lý conflict lớn, quyết định cuối khi có bất đồng |
| Thành viên | Nguyễn Minh Đạt, Nguyễn Hải Yến, Phạm Thành Đạt, Trương Quốc Trường | Code trên nhánh riêng, tự mở PR, không tự merge vào `main` |

**Nguyên tắc quan trọng nhất: không ai push trực tiếp lên `main`.** Mọi thay đổi vào `main` đi qua Pull Request, và chỉ anh Trường merge vào `main`.

---

## Cấu trúc branch

```
main                 # code ổn định, luôn chạy được — chỉ nhận merge qua PR đã review
├── feature/xxx      # 1 branch cho mỗi task/tính năng (ưu tiên gắn Task ID)
├── fix/xxx          # branch sửa bug thông thường
├── hotfix/xxx       # branch sửa lỗi khẩn cấp
└── chore/xxx        # branch phụ trợ (docs, cấu hình, CI/CD)
```

- `main` được CI (`.github/workflows/ci.yml`) tự chạy lint (`ruff`) + test (`pytest`) trên mọi push và PR.
- Không cần giữ `main` "xanh" tuyệt đối 100% thời gian, nhưng PR merge vào `main` phải pass CI và đạt Definition of Done (xem [ADR-0005](adrs/0005-definition-of-done.md)).

### Đặt tên branch (Thống nhất theo AGENTS.md)

Format chuẩn: `<loại>/<TASK-ID>-<mô-tả-ngắn>` hoặc `<loại>/<mô-tả-ngắn>` — dùng gạch ngang `-`, không dấu, viết thường.

| Loại | Dùng khi | Ví dụ chuẩn |
|---|---|---|
| `feature/` | Thêm tính năng mới theo task (bắt buộc gắn Task ID nếu có) | `feature/TASK-010-auth-api`, `feature/TASK-003-dose-event` |
| `fix/` | Sửa bug trong quá trình phát triển / sprint | `fix/TASK-010-cors-error`, `fix/login-session` |
| `hotfix/` | Sửa lỗi nghiêm trọng/khẩn cấp trên môi trường chạy | `hotfix/jwt-expiration`, `hotfix/db-connection` |
| `chore/` | Công việc phụ trợ (docs, dependencies, workflow, config) | `chore/update-readme`, `chore/setup-git-hooks` |

---

## Quy trình làm việc (từng bước)

### 1. Trước khi bắt đầu task mới
```bash
git checkout main
git pull origin main        # luôn kéo mới nhất trước khi tạo branch
git checkout -b feature/TASK-XXX-ten-task
```

### 2. Trong lúc code
- Commit nhỏ, thường xuyên, message tuân thủ [CONVENTIONAL-COMMITS-CHEATSHEET.md](CONVENTIONAL-COMMITS-CHEATSHEET.md):
  `<TASK-ID>: <mô tả ngắn gọn, dạng động từ>` (hoặc `<type>(scope): <description>`).
  Ví dụ: `TASK-010: them endpoint xac thuc otp qua email` hoặc `fix(auth): handle token expiry error`.
- Nếu task kéo dài nhiều ngày, thỉnh thoảng merge `main` mới nhất vào branch của mình để tránh conflict dồn cục:
  ```bash
  git checkout main && git pull origin main
  git checkout feature/TASK-XXX-ten-task
  git merge main
  ```

### 3. Trước khi push — kiểm tra local
```bash
ruff check backend/ tests/
pytest tests/ -v
```
Chạy pass trước khi push, đỡ để CI báo đỏ.

### 4. Push branch
```bash
git push -u origin feature/TASK-XXX-ten-task
```
Push này cũng kích hoạt hook nộp AI log (xem hướng dẫn AI logging đã trao đổi trước đó).

### 5. Mở Pull Request vào `main`
- Trên GitHub, tạo PR từ branch của mình → `main`.
- Mô tả PR: task làm gì, test thế nào, có ảnh hưởng phần nào của người khác không.
- Gắn **anh Trường** làm reviewer.

### 6. Review & merge
- Anh Trường review, có thể yêu cầu sửa trước khi merge.
- Chỉ merge khi: CI pass ✅ + được review approve.
- Merge xong, **xoá branch** (GitHub có nút "Delete branch" sau merge) để repo gọn.

### 7. Sau khi được merge
```bash
git checkout main
git pull origin main
git branch -d feature/ten-task-cua-ban   # xoá branch local
```

---

## Xử lý conflict

- Ưu tiên tự resolve nếu conflict trong phần code của chính mình.
- Nếu conflict với phần code người khác đang phụ trách → nhắn trực tiếp người đó trước khi tự ý sửa.
- Conflict phức tạp không tự tin xử lý → nhờ anh Trường hỗ trợ resolve trước khi merge.

## Quy tắc phụ

- Không commit `.env`, file chứa API key, hay file rác cá nhân (đã có `.gitignore` chặn `.env`, `.ai-log/*.jsonl`).
- 1 PR = 1 task/tính năng rõ ràng, tránh PR gộp nhiều việc không liên quan (khó review).
- Nếu task bị block hoặc trễ deadline, cập nhật trạng thái trong [TEAM.md](TEAM.md) để cả nhóm biết.

---

Xem thêm: [TEAM.md](TEAM.md) (phân công & trạng thái task) · [WORKLOG.md](WORKLOG.md) (log theo ngày)
