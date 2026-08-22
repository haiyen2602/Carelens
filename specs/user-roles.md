# User Roles — VMEC-04

> **Owner:** PM (Nguyễn Hải Yến) · **Cập nhật khi:** thêm/sửa vai trò người dùng cuối của sản phẩm
> Lưu ý: đây là vai trò của **người dùng sản phẩm** (end user), khác với vai trò trong team ở `AGENTS.md` §3 và `TEAM.md`.

## Danh sách vai trò người dùng

| Vai trò | Mô tả | Quyền hạn chính | Thiết bị / UI |
|---|---|---|---|
| `doctor` | Bác sĩ nội khoa/chuyên khoa quản lý nhiều bệnh nhân mãn tính | Tạo & **duyệt** phác đồ; xem preview timeline lịch nhắc; duyệt/từ chối đề xuất đổi lịch của agent; xem dashboard tuân thủ; nhận cảnh báo mức Trung bình & Nghiêm trọng; xem audit log | Web desktop (Next.js) |
| `patient` | Bệnh nhân dùng thuốc dài ngày (chủ yếu cao tuổi, nhiều bệnh nền) hoặc liệu trình ngắn hạn | Nhận nhắc thuốc 3 cấp độ; xác nhận liều bằng ảnh hoặc nút bấm; chat tự nhiên với agent; xem lịch uống thuốc của **chính mình**; hỏi thông tin thuốc | Mobile PWA |
| `caregiver` | Người thân/người chăm sóc bệnh nhân (con cái…) | Duyệt ảnh xác nhận trong 1 giờ khi vision không khớp; xử lý hàng đợi cảnh báo có ngữ cảnh; xem lịch sử/heatmap tuân thủ của bệnh nhân được liên kết; nhận cảnh báo mọi mức từ Trung bình trở lên | Mobile |
| `admin` | Quản trị hệ thống (nội bộ team/demo) | Quản lý tài khoản, liên kết bệnh nhân ↔ bác sĩ ↔ người thân, nạp/cập nhật dữ liệu thuốc cho RAG, xem log hệ thống | Web desktop |

**Quan hệ liên kết (bắt buộc để phân quyền dữ liệu):**

- Một `patient` có **1 bác sĩ phụ trách chính** (`[CẦN CHỐT: có cho phép nhiều bác sĩ không? — quyết trước khi code auth]`) và **0..n caregiver**.
- Một `doctor` quản lý nhiều `patient`.
- Một `caregiver` có thể liên kết nhiều `patient` (VD: chăm cả bố và mẹ).
- **Nguyên tắc dữ liệu:** mọi truy vấn dữ liệu bệnh nhân phải kiểm tra quan hệ liên kết này, không chỉ kiểm tra role. Bác sĩ A **không** được xem dữ liệu bệnh nhân của bác sĩ B.

## Ma trận quyền (Permission matrix)

| Chức năng | `doctor` | `patient` | `caregiver` | `admin` |
|---|---|---|---|---|
| Tạo phác đồ | ✅ | ❌ | ❌ | ❌ |
| **Duyệt** phác đồ (kích hoạt agent) | ✅ | ❌ | ❌ | ❌ |
| Sửa/dừng phác đồ đang chạy | ✅ | ❌ | ❌ | ❌ |
| Xem lịch nhắc của bệnh nhân | ✅ (bệnh nhân của mình) | ✅ (của mình) | ✅ (bệnh nhân liên kết) | ✅ |
| Xác nhận liều bằng ảnh / nút bấm | ❌ | ✅ | ❌ | ❌ |
| Chat với agent | ❌ | ✅ | `[CẦN CHỐT: caregiver có được chat thay không?]` | ❌ |
| Duyệt ảnh xác nhận khi vision không khớp | ❌ | ❌ | ✅ | ❌ |
| Nhận cảnh báo mức **Nhẹ** | ❌ (chỉ ghi log) | ❌ | ❌ | ❌ |
| Nhận cảnh báo mức **Trung bình** | ✅ | ❌ | ✅ | ❌ |
| Nhận cảnh báo mức **Nghiêm trọng** (< 2 phút) | ✅ | ✅ (overlay cấp cứu) | ✅ | ❌ |
| Duyệt đề xuất đổi lịch nhắc của agent | ✅ | ❌ | ❌ | ❌ |
| Xem dashboard tuân thủ (tự khai vs có xác minh) | ✅ | ❌ | ⚠️ bản đơn giản (heatmap) | ✅ |
| Xem audit log hành động của agent | ✅ | ❌ | ❌ | ✅ |
| Nạp/sửa dữ liệu thuốc cho RAG | ❌ | ❌ | ❌ | ✅ |
| Quản lý tài khoản & liên kết | ❌ | ❌ | ❌ | ✅ |

Ký hiệu: ✅ được phép · ❌ không được phép · ⚠️ được phép ở mức giới hạn

> **Đã chốt (2026-08-20):** ô "Tạo phác đồ" của `caregiver` là ❌ **có chủ đích** — chỉ bác sĩ mới được tạo và duyệt phác đồ, kể cả khi người thân có toa giấy trong tay. Phác đồ là dữ liệu lâm sàng; để người không có chuyên môn nhập vào sẽ phá vỡ nguyên tắc Human-in-the-loop (ADR-0010) và mở thêm rủi ro kiểm soát danh mục thuốc (FB-14). Hệ quả là sản phẩm có cold-start với người thân — cách xử lý ở phía thông điệp sản phẩm xem [`product-vision.md`](./product-vision.md) §2.1. **Không sửa ô này thành ✅ nếu chưa có quyết định mới của PM.**

## Điều KHÔNG vai trò nào được làm

Áp dụng cho **mọi** role, kể cả `admin` — đây là ràng buộc an toàn của sản phẩm (xem `product-vision.md` §4 Out of scope):

- Không ai (kể cả agent) được để **agent tự kê đơn, đổi thuốc, đổi liều, hoặc chẩn đoán**.
- Không ai được sửa/xoá bản ghi `audit_log`.
- Không ai được vô hiệu hoá `safety` layer từ phía UI.

---
**Lưu ý cho AI:** Khi implement bất kỳ tính năng nào có kiểm soát quyền truy cập, phải đối chiếu đúng bảng quyền ở trên **và** quan hệ liên kết ở mục trên (role đúng nhưng không liên kết với bệnh nhân đó thì vẫn phải từ chối). Không tự suy diễn quyền hạn nếu chưa được định nghĩa rõ (các ô `[CẦN CHỐT]`) — hỏi lại PM.
