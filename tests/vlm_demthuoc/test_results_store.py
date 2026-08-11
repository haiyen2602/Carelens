"""Kiểm chứng phần ghi/đọc kết quả của chương trình đếm thuốc.

Bộ test này ra đời cùng lúc với việc tách `camera_counter.py` (2026-08-10) và
mục đích chính là LƯỚI AN TOÀN cho lần tách đó: chứng minh hành vi lưu trữ
không đổi sau khi code được chia ra nhiều file.

Không cần webcam, không gọi API — toàn bộ chạy trên `tmp_path` của pytest.
"""

import json
import time

import pytest
from prompts import COUNT_KEYS, COUNT_LABELS_VI, NON_DRUG_KEY
from results_store import (
    append_log,
    build_record,
    load_results_json,
    next_run_index,
    print_result,
    save_results_json,
)
from vlm_client import CountResult


def _ok_result(**kwargs) -> CountResult:
    """Một kết quả đếm thành công, mọi loại đều có số khác 0 để nhìn ra ngay
    nếu một dòng bị in thiếu."""
    counts = {key: index + 1 for index, key in enumerate(COUNT_KEYS)}
    defaults = dict(
        ok=True,
        counts=counts,
        khong_phai_thuoc=0,
        do_tin_cay="cao",
        ghi_chu="",
        latency_sec=1.25,
    )
    defaults.update(kwargs)
    return CountResult(**defaults)


# ---------------------------------------------------------------------------
# print_result — sinh dòng từ COUNT_KEYS, không viết cứng
# ---------------------------------------------------------------------------
def test_in_du_moi_loai_thuoc_khai_bao_trong_count_keys(capsys):
    """Đây là bài test bảo vệ đúng lỗi đã sửa: bản cũ viết cứng 6 lệnh print,
    nên thêm loại thuốc thứ 7 vào COUNT_KEYS là terminal bỏ sót im lặng.
    Test đi qua COUNT_KEYS nên tự bao phủ loại mới mà không cần sửa test."""
    print_result(_ok_result(), index=1)
    out = capsys.readouterr().out

    for key in COUNT_KEYS:
        assert COUNT_LABELS_VI[key] in out, f"thiếu dòng cho loại {key!r}"


def test_moi_khoa_trong_count_keys_deu_co_nhan_tieng_viet():
    """Nếu ai thêm khoá vào COUNT_KEYS mà quên thêm nhãn, print_result sẽ ném
    KeyError lúc chạy thật. Bắt ở đây rẻ hơn nhiều."""
    for key in (*COUNT_KEYS, NON_DRUG_KEY):
        assert key in COUNT_LABELS_VI


def test_in_dung_so_luong_cua_tung_loai(capsys):
    result = _ok_result()
    print_result(result, index=3)
    out = capsys.readouterr().out

    for key in COUNT_KEYS:
        assert f"{COUNT_LABELS_VI[key]}" in out
        assert str(result.counts[key]) in out
    # vien_nang(1) + vien_nen(2)
    assert "Tổng số viên (nang + nén): 3" in out


def test_ket_qua_loi_chi_in_loi_khong_in_bang_so(capsys):
    print_result(CountResult(ok=False, error="hết hạn mức"), index=2)
    out = capsys.readouterr().out

    assert "LỖI: hết hạn mức" in out
    assert "Tổng số viên" not in out


def test_dong_da_loai_ra_chi_hien_khi_co_keo_bi_loai(capsys):
    print_result(_ok_result(khong_phai_thuoc=0), index=1)
    assert "Đã loại ra" not in capsys.readouterr().out

    print_result(_ok_result(khong_phai_thuoc=4), index=2)
    out = capsys.readouterr().out
    assert "Đã loại ra : 4" in out


def test_ghi_chu_rong_thi_khong_in_dong_ghi_chu(capsys):
    print_result(_ok_result(ghi_chu=""), index=1)
    assert "Ghi chú" not in capsys.readouterr().out

    print_result(_ok_result(ghi_chu="ảnh hơi mờ"), index=2)
    assert "Ghi chú    : ảnh hơi mờ" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# load_results_json — ưu tiên KHÔNG làm mất dữ liệu cũ
# ---------------------------------------------------------------------------
def test_file_chua_ton_tai_thi_bat_dau_bang_danh_sach_rong(tmp_path):
    assert load_results_json(tmp_path / "chua_co.json") == []


def test_doc_lai_duoc_ket_qua_lan_chay_truoc(tmp_path):
    path = tmp_path / "ket_qua.json"
    path.write_text(json.dumps([{"lan": 1}, {"lan": 2}]), encoding="utf-8")

    assert load_results_json(path) == [{"lan": 1}, {"lan": 2}]


def test_file_hong_duoc_giu_lai_chu_khong_bi_ghi_de(tmp_path):
    """Yêu cầu quan trọng nhất của hàm này: một lỗi đọc KHÔNG được phép làm mất
    kết quả đã đếm của những lần chạy trước."""
    path = tmp_path / "ket_qua.json"
    path.write_text("{ day khong phai json hop le", encoding="utf-8")

    assert load_results_json(path) == []

    backups = list(tmp_path.glob("ket_qua_hong_*.json"))
    assert len(backups) == 1, "file hỏng phải được đổi tên giữ lại"
    assert "khong phai json" in backups[0].read_text(encoding="utf-8")
    assert not path.exists(), "file gốc phải được dời đi để bắt đầu file mới"


def test_json_dung_cu_phap_nhung_khong_phai_mang_cung_duoc_giu_lai(tmp_path):
    path = tmp_path / "ket_qua.json"
    path.write_text(json.dumps({"day_la": "object"}), encoding="utf-8")

    assert load_results_json(path) == []
    assert list(tmp_path.glob("ket_qua_hong_*.json"))


def test_bo_qua_phan_tu_khong_phai_dict(tmp_path):
    path = tmp_path / "ket_qua.json"
    path.write_text(json.dumps([{"lan": 1}, "rac", 42, None]), encoding="utf-8")

    assert load_results_json(path) == [{"lan": 1}]


# ---------------------------------------------------------------------------
# save_results_json — ghi tạm rồi đổi tên
# ---------------------------------------------------------------------------
def test_ghi_xong_khong_de_lai_file_tam(tmp_path):
    path = tmp_path / "ket_qua.json"
    save_results_json(path, [{"lan": 1}])

    assert json.loads(path.read_text(encoding="utf-8")) == [{"lan": 1}]
    assert not (tmp_path / "ket_qua.json.tmp").exists()


def test_tu_tao_thu_muc_cha_neu_chua_co(tmp_path):
    path = tmp_path / "chua" / "co" / "ket_qua.json"
    save_results_json(path, [])

    assert path.is_file()


def test_ghi_roi_doc_lai_ra_dung_du_lieu(tmp_path):
    """Vòng khép kín save -> load: đây là đường đi thật của chương trình giữa
    hai lần chạy."""
    path = tmp_path / "ket_qua.json"
    records = [{"lan": 1, "phien": "A", "vien_nen": 5}]

    save_results_json(path, records)
    assert load_results_json(path) == records


# ---------------------------------------------------------------------------
# build_record
# ---------------------------------------------------------------------------
def test_ban_ghi_thanh_cong_co_du_so_lieu_va_khong_lap_thoi_gian(tmp_path):
    record = build_record(_ok_result(), index=7, image_path=tmp_path / "a.jpg", phien="P1")

    assert record["lan"] == 7
    assert record["phien"] == "P1"
    assert record["anh"] == "a.jpg"
    assert record["thanh_cong"] is True
    assert record["tong_vien"] == 3
    # to_dict() cũng có "thoi_gian"; chỉ được giữ đúng một, lấy từ `common`.
    assert isinstance(record["thoi_gian"], str)


def test_ban_ghi_loi_giu_nguyen_van_loi_va_khong_co_so_dem(tmp_path):
    record = build_record(
        CountResult(ok=False, error="timeout"), index=2, image_path=None, phien="P1"
    )

    assert record["thanh_cong"] is False
    assert record["loi"] == "timeout"
    assert record["anh"] == ""
    assert "tong_vien" not in record


def test_ban_ghi_luon_serialize_duoc_ra_json(tmp_path):
    """Bản ghi đi thẳng vào json.dumps ở save_results_json — kiểu dữ liệu lạ
    lọt vào đây sẽ làm hỏng cả file kết quả."""
    record = build_record(_ok_result(), index=1, image_path=tmp_path / "b.jpg", phien="P")
    json.dumps(record, ensure_ascii=False)  # không được ném exception


# ---------------------------------------------------------------------------
# next_run_index — đánh số nối tiếp file cũ
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "records, mong_doi",
    [
        ([], 0),
        ([{"lan": 1}, {"lan": 2}], 2),
        ([{"lan": 5}, {"lan": 3}], 5),          # không giả định đã sắp xếp
        ([{"khong_co_truong_lan": 1}], 0),
        ([{"lan": "hai"}, {"lan": 4}], 4),      # bỏ qua giá trị không phải số
        ([{"lan": True}, {"lan": 2}], 2),       # bool là int trong Python
    ],
)
def test_so_thu_tu_tiep_theo_noi_tiep_file_cu(records, mong_doi):
    assert next_run_index(records) == mong_doi


# ---------------------------------------------------------------------------
# append_log
# ---------------------------------------------------------------------------
def test_moi_lan_dem_them_mot_dong_jsonl(tmp_path):
    path = tmp_path / "log.jsonl"
    append_log(path, _ok_result())
    append_log(path, CountResult(ok=False, error="hỏng"))

    dong = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(dong) == 2
    assert json.loads(dong[0])["tong_vien"] == 3
    assert json.loads(dong[1])["loi"] == "hỏng"


def test_dong_log_cua_ket_qua_loi_van_co_thoi_gian(tmp_path):
    path = tmp_path / "log.jsonl"
    append_log(path, CountResult(ok=False, error="x", timestamp=time.time()))

    ban_ghi = json.loads(path.read_text(encoding="utf-8").strip())
    assert "thoi_gian" in ban_ghi
