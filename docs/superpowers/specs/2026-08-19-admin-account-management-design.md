# Thiết kế: Quản lý tài khoản Admin

## Phạm vi

Hoàn thiện trang `frontend/src/app/admin/accounts/page.tsx` trên API tài khoản hiện có. Không thay đổi kiến trúc hoặc mở rộng contract backend.

## Trải nghiệm người dùng

- Trang có ba mục con dạng tab: `Bệnh nhân`, `Bác sĩ`, `Admin`.
- Tab `Bệnh nhân` hiển thị cả tài khoản `patient` và `caregiver`; caregiver không có tab riêng và được hiển thị trong nhóm Bệnh nhân.
- Tab `Bác sĩ` chỉ hiển thị `doctor`; tab `Admin` chỉ hiển thị `admin`.
- Mỗi tab có tìm kiếm theo họ tên/email và lọc trạng thái `Tất cả`, `Hoạt động`, `Đã khoá`.
- Bảng giữ các cột tài khoản, vai trò, email, liên kết, trạng thái và thao tác khoá/mở khoá.
- Hiển thị trạng thái loading, lỗi tải dữ liệu và danh sách rỗng.
- Nút `Tạo tài khoản` chỉ xuất hiện ở tab Bác sĩ và Admin.

## Tạo tài khoản

Dialog tạo tài khoản gồm đúng các trường: họ tên, email, mật khẩu và vai trò.

- Vai trò được phép chọn chỉ là `doctor` hoặc `admin`.
- Không hiển thị và không gửi `patient_id` hoặc `doctor_id`.
- Validate bắt buộc họ tên/email/mật khẩu; mật khẩu tối thiểu 8 ký tự.
- Gọi `createAccount` với payload hiện có, chỉ truyền role doctor/admin và cập nhật lại danh sách sau khi thành công.
- Hiển thị lỗi API trong dialog, đóng và reset form sau khi tạo thành công.

## Trạng thái tài khoản

Thao tác khoá/mở khoá dùng `updateAccountStatus` hiện có. Sau khi thành công, invalidation query `accounts` làm mới bảng. Caregiver cũng được phép khoá/mở khoá khi xuất hiện trong tab Bệnh nhân.

## Dữ liệu và ranh giới

- Tải toàn bộ danh sách một lần bằng `listAccounts`, sau đó lọc theo tab, từ khoá và trạng thái ở client.
- Không thêm endpoint, field hoặc thay đổi response contract.
- Không sửa các màn hình admin khác.

## Kiểm thử và xác minh

- Kiểm tra tĩnh TypeScript/ESLint/build theo script frontend hiện có.
- Kiểm tra thủ công các tab, tìm kiếm, lọc, tạo doctor/admin, loại caregiver khỏi các tab khác, và khoá/mở khoá.
- Đảm bảo trạng thái loading/error/empty không làm vỡ layout.
