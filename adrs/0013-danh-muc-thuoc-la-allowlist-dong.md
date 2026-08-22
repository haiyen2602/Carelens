# ADR-0013: Danh mục thuốc là allowlist đóng

**Status:** Accepted
**Ngày:** 2026-08-21
**Người đề xuất:** Nguyễn Hải Yến + AI
**Người duyệt:** `[chờ Architect/Tech Lead review]`

## Bối cảnh (Context)

Ô nhập tên thuốc ở form kê đơn là text tự do có gợi ý. `PrescriptionItemIn.drug_id` cho phép rỗng, và
`_chuan_hoa_item()` cố ý cho qua khi rỗng — docstring cũ ghi rõ lý do: *"Chặn hẳn ở đây thì bác sĩ
không kê nổi thuốc mới chưa kịp vào danh mục."*

Hệ quả là **gõ được tên bất kỳ vào đơn thuốc**. Reviewer phát hiện tại buổi review (FB-14, mức
Critical): hệ thống cho phép xuất hiện các tên như Heroin/diacetylmorphine trong đơn. Đây không phải
lỗi lập trình mà là hệ quả trực tiếp của một quyết định thiết kế có chủ đích.

Kiểm tra DB dev ngày 2026-08-21 cho thấy vấn đề đã hiện thực hoá: 3 phác đồ có dòng thuốc thiếu
`drug_id`, trong đó **hai đơn đang ở trạng thái `active` với "tên thuốc" là `"ấ"` và `"aaaaaaa"`**.

Ngoài ra còn một lỗ hổng thứ hai chưa ai nêu: khi có `drug_id`, danh mục chỉ thắng ở `dang_thuoc` và
`duong_dung`, còn `ten_thuoc` vẫn lấy chữ bác sĩ gõ. Chọn một thuốc hợp lệ rồi sửa lại ô tên là ghi
được tên bất kỳ xuống đơn — và đó chính là tên bệnh nhân nhìn thấy.

## Quyết định (Decision)

1. **Danh mục thuốc là allowlist đóng.** `drug_id` bắt buộc. Không có `drug_id` thì không kê được,
   không có ngoại lệ trong luồng kê đơn.
2. **Danh mục thắng mọi trường định danh** — `ten_thuoc`, `dang_thuoc`, `duong_dung`, `ham_luong` đều
   đọc lại từ danh mục, bỏ hoàn toàn giá trị trình duyệt gửi lên.
3. **Đường thoát là quy trình, không phải ngoại lệ kỹ thuật:** bác sĩ gửi yêu cầu bổ sung → admin
   duyệt → mới kê được (bảng `drug_request`, migration 0031). **Chỉ admin được duyệt.**
4. **Caregiver không được nhập phác đồ** dưới bất kỳ hình thức nào (xem `user-roles.md`).

## Vì sao (Rationale)

Quyết định cũ tối ưu cho **sự thuận tiện của bác sĩ**; quyết định này tối ưu cho **an toàn của bệnh
nhân**. Với một sản phẩm y tế, khi hai thứ đó xung đột thì an toàn thắng.

Lý do cũ vẫn có giá trị — bác sĩ kẹt với thuốc ngoài danh mục là vấn đề thật, không phải tưởng tượng.
Vì vậy quyết định này **bắt buộc đi kèm đường thoát**; siết mà không mở đường đi tiếp thì sẽ có người
hoàn tác, và lỗ hổng quay lại.

Các phương án đã cân nhắc và loại bỏ:

- **Giữ nguyên, chỉ thêm cảnh báo trên UI.** Loại: cảnh báo không phải là kiểm soát, và API vẫn nhận
  được request tự do từ bất kỳ client nào.
- **Denylist thay vì allowlist.** Loại: không thể liệt kê hết cái xấu. Danh mục 3.562 thuốc đủ rộng
  để allowlist không quá chặt.
- **Duyệt xong thì `INSERT` vào bảng `drug`.** Loại: bảng đó được nạp lại từ artifact bằng
  `seed_drug_catalog.py`, dòng thêm tay sẽ bị xoá ở lần nạp lại kế tiếp — hỏng âm thầm.
- **Duyệt xong thì xuất lại artifact JSONL + redeploy.** Loại: đúng "một nguồn sự thật" nhưng bác sĩ
  phải chờ deploy mới kê được, không dùng được trong thực tế.

## Vì sao thân thiện với AI + Team

- Quy tắc phát biểu được bằng một câu, không có trường hợp ngoại lệ phải nhớ: *không có `drug_id` thì
  không kê được.*
- Chỉ có **một chốt chặn** (`_chuan_hoa_item`) cho cả hai đường ghi (tạo mới và sửa phác đồ), nên
  người đọc code sau này không phải đi tìm xem còn chỗ nào chưa chặn.
- Docstring tại chỗ ghi rõ đây là lý do an toàn chứ không phải tiện lợi, kèm mã feedback — người sau
  muốn nới lỏng sẽ đọc được vì sao không nên.

## Hệ quả (Consequences)

**Tích cực:**

- Không còn đường ghi tên thuốc tự do vào đơn.
- Tên hiển thị cho bệnh nhân luôn khớp với thuốc thật sự được kê.
- Mọi thuốc ngoài danh mục đều để lại dấu vết: ai xin, ai duyệt, lúc nào.

**Đánh đổi / rủi ro:**

- **Đây là cổng người, không phải allowlist.** Đường `drug_request` mở lại lối ghi tên tự do, chỉ khác
  là có admin đứng giữa. Admin bấm duyệt qua loa là mở lại FB-14. Denylist chất bị kiểm soát thu hẹp
  bề mặt chứ không đóng lại được.
- **Danh sách chất bị kiểm soát hiện là tập khởi đầu do dev đặt**, chưa trích từ văn bản pháp quy —
  đã đánh dấu `[CẦN CHỐT]` trong `controlled_substances.py`, cần người có chuyên môn y tế soát.
- **Thêm một nguồn sự thật cho danh mục.** Nguồn lâu dài vẫn phải là artifact Canonical V2
  (ADR-0012); `drug_request` là cầu tạm. Tiền tố `req-` giúp lọc đúng tập cần gộp ngược sau này.
- **Chatbot không trả lời được về thuốc duyệt qua đường này** — chúng không có dòng nào trong
  `drug_chunks`. Việc sinh chunk + embedding thuộc mảng RAG, tách task riêng.
- **Dữ liệu cũ thiếu `drug_id` sẽ không sửa/duyệt lại được.** Phải đếm và xử lý trước khi deploy.
- Bác sĩ mất thêm một bước khi gặp thuốc ngoài danh mục — chấp nhận có chủ đích.

## Câu chốt

> Bác sĩ chọn thuốc từ danh mục, không gõ thuốc vào danh mục.
