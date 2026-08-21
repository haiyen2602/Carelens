# Bug: `alembic upgrade` báo thành công nhưng không ghi gì vào DB

> **Gửi:** Trương Quốc Trường (Tech Lead)
> **Người báo:** Nguyễn Hải Yến · **Ngày:** 2026-08-21
> **Mức độ:** Cao — ảnh hưởng mọi lần deploy production
> **File:** [`migrations/env.py`](../migrations/env.py) · **Đến từ:** PR thêm khối `[ALEMBIC AUTO-HEAL]`

## Tóm tắt

`alembic upgrade head` in đủ log `Running upgrade 0030 -> 0031`, thoát code 0, nhưng **`alembic_version` không đổi và bảng mới không được tạo**. Không có thông báo lỗi nào.

`railway.json` gọi `python scripts/safe_migrate.py` ở `preDeployCommand`, và script đó cũng đi qua `env.py` này. Nghĩa là **deploy production đang báo migrate thành công trong khi không migrate gì**.

Hệ quả cụ thể đã quan sát được: sau khi merge main, `tests/test_nudge_routes.py` đỏ với `relation "nudge" does not exist` — migration `0030_nudge` không hề được áp dụng dù script báo thành công.

## Tái hiện

```bash
export DATABASE_URL=<postgres dev>
python -m alembic upgrade head
# Log: INFO [alembic.runtime.migration] Running upgrade 0030 -> 0031
# Exit code: 0

psql -c "SELECT version_num FROM alembic_version"   # -> van la 0030
psql -c "SELECT to_regclass('public.drug_request')" # -> NULL
```

Đối chứng: thay tạm `migrations/env.py` bằng bản trước khi thêm khối auto-heal → cùng lệnh, cùng DB, migration áp dụng đúng.

## Nguyên nhân

Khối `[ALEMBIC AUTO-HEAL]` ([env.py:41-63](../migrations/env.py#L41-L63)) chạy `inspect(connection)` và một câu `SELECT` **trước** `context.configure()`. Trong SQLAlchemy 2.0, chỉ cần đọc là đã mở một transaction ngầm trên connection đó.

Đo trực tiếp:

```
sau khi doc, in_transaction() = True
connection.begin() -> InvalidRequestError:
    This connection has already initialized a SQLAlchemy Transaction() object via begin()
bang co ton tai sau khi thoat khoi connection: False
```

Alembic không crash vì `context.begin_transaction()` thấy connection đã có transaction thì trả về một context rỗng thay vì tự mở. Migration chạy bên trong transaction ngầm mà **không ai commit**, và SQLAlchemy rollback khi đóng connection. DDL *đã thực thi* — nên log có in — nhưng bị huỷ ngay sau đó.

**Quan trọng:** lỗi xảy ra ở **mọi lần chạy**, không chỉ khi cần auto-heal. Riêng thao tác đọc của inspector đã đủ mở transaction. DB ở revision hợp lệ vẫn dính.

## Cách sửa đề xuất

**Cách A — dùng connection riêng cho khối auto-heal** *(khuyến nghị)*

```python
with connectable.connect() as heal_conn:
    ...kiểm tra và UPDATE...
    heal_conn.commit()

with connectable.connect() as connection:   # connection sạch, alembic tự làm chủ transaction
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
```

**Cách B — thêm `connection.rollback()`** ngay trước `context.configure()`.

Đã thử cả hai trên Postgres dev, cả hai đều làm migration ghi được. Nghiêng về A: B chỉ là một dòng trông vô nghĩa, người sau rất dễ xoá và tái lập bug.

## Một vấn đề riêng, cần anh quyết

Bản thân logic auto-heal đáng xem lại: khi gặp revision lạ, nó **stamp thẳng lên head**, tức đánh dấu *mọi migration đã chạy* trong khi thực tế chưa chạy cái nào. Schema sẽ thiếu bảng nhưng alembic tin là đủ — hỏng tệ hơn cả bug hiện tại và khó phát hiện hơn.

Em không tự sửa phần này vì nó là đảo một quyết định thiết kế, không phải vá lỗi.

Ngoài ra `f"UPDATE alembic_version SET version_num = '{head_rev}'"` đang nội suy chuỗi vào SQL. `head_rev` lấy từ chính repo nên không phải lỗ hổng thực tế, nhưng nên đổi sang tham số ràng buộc.

## Đã xác nhận trên PRODUCTION (2026-08-21)

Chạy qua `railway ssh` trên môi trường production:

```
alembic_version : 0029
bang nudge        : None
bang health_log   : None
bang drug_request : None
```

**Production đang ở revision `0029`, trong khi `main` đã ở `0030`.** Migration `0030_nudge` chưa
bao giờ được áp dụng dù các lần deploy đều báo thành công.

Hệ quả đang xảy ra: tính năng nudge (nhắc nhẹ từ người thân) đã merge vào `main` và đã deploy,
nhưng **bảng `nudge` không tồn tại trên production** — mọi request tới nó sẽ lỗi. Bảng
`health_log` cũng không có.

Đây không còn là rủi ro lý thuyết nữa.

## Việc cần làm trước lần deploy tới

1. Sửa phần transaction (A hoặc B).
2. Sau khi sửa, **chạy lại migration trên production** để đưa từ `0029` lên head. Kiểm tra `nudge` và `health_log` đã được tạo.
3. Quyết định về logic auto-heal.
