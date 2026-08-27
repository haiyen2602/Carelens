# TASK-ONBOARDING-PROFILE-COMPLETION: Hoàn tất hồ sơ bệnh nhân một lần

**Domain:** Auth / Patient profile
**Owner:** Nguyễn Hải Yến + AI
**Sprint:** To be assigned
**Status:** In Progress

## Mục tiêu

Chỉ hiển thị `/onboarding/profile` sau khi đăng ký thành công và ở lần đăng nhập đầu tiên khi
hồ sơ bệnh nhân chưa đầy đủ trong database. Khi đã lưu thành công, các lần đăng nhập sau đi
thẳng vào khu vực bệnh nhân.

## Acceptance Criteria

- [x] Sáu trường ngày sinh, số điện thoại, địa chỉ, giới tính, chiều cao và cân nặng là bắt buộc
  để hoàn tất hồ sơ.
- [x] Backend là nguồn sự thật: chỉ đặt `profile_completed=true` khi sáu giá trị hợp lệ đã được
  lưu; không cho thao tác cập nhật làm mất trạng thái hoàn tất.
- [x] Onboarding nạp lại hồ sơ đang lưu, dùng kết quả DB để quyết định redirect và không buộc
  người dùng nhập lại dữ liệu đã có.
- [x] Sau lưu thành công, session được đồng bộ và lần đăng nhập sau không quay lại onboarding.
- [ ] Có regression test backend và frontend contract test; lint, type-check, build theo scope pass.

## Context đã đọc

- [x] `AGENTS.md`
- [x] `specs/user-roles.md`
- [x] `specs/business-rules.md`
- [x] `specs/api-contracts.md`
- [x] `adrs/0004-project-structure-and-coding-convention.md`
- [x] `adrs/0005-definition-of-done.md`
- [x] `adrs/0010-human-in-the-loop.md`
- [x] `CONVENTIONAL-COMMITS-CHEATSHEET.md`

## Ghi chú production

- Kiểm tra read-only ngày 2026-08-27: `profile_completed=false` 33 hồ sơ, `true` 56 hồ sơ;
  không có hồ sơ đã đủ bốn trường bắt buộc cũ nhưng cờ vẫn `false`.
- Không cần migration mới: các cột hồ sơ đã có trong bảng `patient`.
- Kiểm tra 2026-08-28: frontend contract test, scoped ESLint, TypeScript và Ruff pass. Regression
  backend mới đã được thêm; container tạm không kết nối được database local nên test bị skip và cần
  chạy lại trong CI hoặc môi trường Docker có DB truy cập được.
