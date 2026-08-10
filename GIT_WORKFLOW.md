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
└── feature/xxx      # 1 branch cho mỗi task/tính năng
└── fix/xxx          # branch sửa bug
```

- `main` được CI (`.github/workflows/ci.yml`) tự chạy lint (`ruff`) + test (`pytest`) trên mọi push và PR.
- Không cần giữ `main` "xanh" tuyệt đối 100% thời gian, nhưng PR merge vào `main` phải pass CI.

### Đặt tên branch

Format: `<loại>/<mô-tả-ngắn>` — dùng gạch ngang, không dấu, viết thường.

| Loại | Dùng khi | Ví dụ |
|---|---|---|
| `feature/` | Thêm tính năng mới | `feature/langgraph-agent`, `feature/chat-ui` |
| `fix/` | Sửa bug | `fix/api-cors-error` |
| `chore/` | Việc phụ trợ (docs, config, refactor nhỏ) | `chore/update-readme` |

---

## Quy trình làm việc (từng bước)

### 1. Trước khi bắt đầu task mới
```bash
git checkout main
git pull origin main        # luôn kéo mới nhất trước khi tạo branch
git checkout -b feature/ten-task-cua-ban
```

### 2. Trong lúc code
- Commit nhỏ, thường xuyên, message rõ ràng (vd. `feat: add PDF parser tool`, `fix: handle empty query in agent`).
- Nếu task kéo dài nhiều ngày, thỉnh thoảng merge `main` mới nhất vào branch của mình để tránh conflict dồn cục:
  ```bash
  git checkout main && git pull origin main
  git checkout feature/ten-task-cua-ban
  git merge main
  ```

### 3. Trước khi push — kiểm tra local
```bash
ruff check src/ tests/
pytest tests/ -v
```
Chạy pass trước khi push, đỡ để CI báo đỏ.

### 4. Push branch
```bash
git push -u origin feature/ten-task-cua-ban
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
