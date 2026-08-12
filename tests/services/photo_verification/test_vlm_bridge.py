"""Kiểm chứng logic gọi mô hình đếm thuốc — KHÔNG gọi mạng thật.

`openai.OpenAI` bị thay bằng một client giả có thể lập trình được: trả về
đúng chuỗi phản hồi mà `api.vilao.ai` từng trả (đã đo thật trong lúc debug) —
rỗng rồi mới thành công, ném BadRequestError khi không hỗ trợ response_format,
hoặc trả rỗng mãi mãi. Mỗi kịch bản ở đây từng là một lỗi THẬT gặp phải, không
phải suy đoán trước.

Không cần DB, không cần mạng — chạy trong vài chục mili giây (trừ hai test cố
ý đo `time.sleep` giữa các lần thử lại).
"""

import json

import httpx
import openai
import pytest

from backend.config import Settings
from backend.services.photo_verification.vlm_bridge import (
    MAX_ANH_BYTES,
    dem_thuoc_trong_anh,
)

ANH_GIA = b"\xff\xd8\xff" + b"0" * 100  # header JPEG gia, du de qua kiem tra dung luong


def _cai_dat(**ghi_de) -> Settings:
    mac_dinh = {
        "internal_auth_secret": "test-secret",
        "vlm_api_key": "sk-test",
        "vlm_provider": "openai",
        "vlm_base_url": "https://vlm.test/v1",
        "vlm_model": "model-test",
        "vlm_json_mode": "schema",
        "vlm_retries": 3,
        "vlm_timeout": 5.0,
        # 0: khong ngu that giua cac lan thu lai trong test.
        "vlm_retry_delay": 0.0,
    }
    return Settings(**{**mac_dinh, **ghi_de})


def _phan_hoi_hop_le(**ghi_de) -> dict:
    payload = {
        "vien_nang": 0, "vien_nen": 2, "tuyp_thuoc": 0, "lo_thuoc": 0,
        "hop_thuoc": 0, "goi_thuoc": 0, "khong_phai_thuoc": 0,
        "do_tin_cay": "cao", "ghi_chu": "ro net",
        **ghi_de,
    }
    return {
        "choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }


class _KetQuaGia:
    """Giả một ChatCompletion đã parse được — chỉ cần .choices và .usage.

    Kiểu SSE-thô-chưa-parse KHÔNG dùng lớp này: `_doc_phan_hoi` kiểm
    `isinstance(response, str)`, nên kịch bản đó phải nạp thẳng một `str`
    vào hàng đợi của `_ClientGia`, không phải bọc trong object.
    """

    def __init__(self, data: dict):
        self.choices = [_Lua(c) for c in data.get("choices", [])]
        self.usage = _Ns(**data.get("usage", {}))


class _Ns:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Lua:
    def __init__(self, choice: dict):
        self.finish_reason = choice.get("finish_reason", "stop")
        self.message = _Ns(content=choice.get("message", {}).get("content", ""))


class _ClientGia:
    """Thay `openai.OpenAI(...)` — `goi_lan_luot` là danh sách kết quả trả về
    theo đúng thứ tự gọi, mỗi phần tử là KetQuaGia hoặc một Exception để ném ra."""

    def __init__(self, goi_lan_luot: list):
        self._hang_doi = list(goi_lan_luot)
        self.so_lan_goi = 0
        self.chat = _Ns(completions=_Ns(create=self._create))

    def _create(self, **_kwargs):
        self.so_lan_goi += 1
        if not self._hang_doi:
            raise AssertionError("Gọi nhiều hơn số lần đã lập trình sẵn")
        ket_qua = self._hang_doi.pop(0)
        if isinstance(ket_qua, Exception):
            raise ket_qua
        return ket_qua


def _gan_client_gia(monkeypatch, goi_lan_luot: list) -> _ClientGia:
    client = _ClientGia(goi_lan_luot)
    monkeypatch.setattr(openai, "OpenAI", lambda **_kw: client)
    return client


def _loi_openai(cls, message: str, status: int = 400):
    req = httpx.Request("POST", "https://vlm.test/v1/chat/completions")
    resp = httpx.Response(status, request=req, json={"error": {"message": message}})
    return cls(message, response=resp, body=None)


# ---------------------------------------------------------------------------
# Chặn ở lối vào, không cần gọi mạng
# ---------------------------------------------------------------------------
def test_anh_rong_bi_tu_choi():
    ket_qua = dem_thuoc_trong_anh(b"", settings=_cai_dat())

    assert not ket_qua.ok
    assert "rỗng" in ket_qua.error


def test_anh_qua_lon_bi_tu_choi():
    ket_qua = dem_thuoc_trong_anh(b"x" * (MAX_ANH_BYTES + 1), settings=_cai_dat())

    assert not ket_qua.ok
    assert "quá lớn" in ket_qua.error


def test_nha_cung_cap_khong_phai_openai_chua_ho_tro():
    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat(vlm_provider="claude"))

    assert not ket_qua.ok
    assert "claude" in ket_qua.error.lower()


def test_thieu_model_bi_tu_choi():
    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat(vlm_model=""))

    assert not ket_qua.ok
    assert "VLM_MODEL" in ket_qua.error


# ---------------------------------------------------------------------------
# Đường thành công
# ---------------------------------------------------------------------------
def test_goi_thanh_cong_tra_ve_dung_so_dem(monkeypatch):
    _gan_client_gia(monkeypatch, [_KetQuaGia(_phan_hoi_hop_le(vien_nen=3))])

    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat())

    assert ket_qua.ok
    assert ket_qua.counts["vien_nen"] == 3
    assert ket_qua.do_tin_cay == "cao"
    assert ket_qua.tong_vien == 3


def test_ghi_chu_va_khong_phai_thuoc_duoc_giu_lai(monkeypatch):
    _gan_client_gia(
        monkeypatch,
        [_KetQuaGia(_phan_hoi_hop_le(khong_phai_thuoc=2, ghi_chu="2 vien keo xylitol"))],
    )

    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat())

    assert ket_qua.khong_phai_thuoc == 2
    assert "keo" in ket_qua.ghi_chu


# ---------------------------------------------------------------------------
# Thử lại khi phản hồi rỗng — đúng kiểu hỏng đo được thật trên api.vilao.ai
# ---------------------------------------------------------------------------
def test_rong_roi_moi_thanh_cong_thi_van_tra_ve_ket_qua(monkeypatch):
    client = _gan_client_gia(
        monkeypatch,
        [
            "",  # lần 1: body rỗng hoàn toàn, SDK trả lại chuỗi thô
            _KetQuaGia({"choices": [], "usage": {}}),  # lần 2: không có choices
            _KetQuaGia(_phan_hoi_hop_le(vien_nang=1)),  # lần 3: thành công
        ],
    )

    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat(vlm_retries=3))

    assert ket_qua.ok
    assert ket_qua.counts["vien_nang"] == 1
    assert client.so_lan_goi == 3


def test_het_luot_thu_van_rong_thi_bao_loi_ro_rang(monkeypatch):
    _gan_client_gia(monkeypatch, [_KetQuaGia({"choices": [], "usage": {}})] * 3)

    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat(vlm_retries=3))

    assert not ket_qua.ok
    assert "rỗng" in ket_qua.error or "không đọc được" in ket_qua.error.lower()


def test_sse_tho_van_duoc_thu_lai(monkeypatch):
    """api.vilao.ai trả luồng SSE ngay cả khi không yêu cầu stream — SDK
    openai không parse được nên trả lại CHUỖI THÔ thay vì object đã parse.
    Đây là kiểu hỏng phổ biến nhất đo được thật trên endpoint đó."""
    client = _gan_client_gia(
        monkeypatch,
        [
            "data: {}\n\ndata: [DONE]\n",  # SSE rỗng, đúng dạng vilao trả về
            _KetQuaGia(_phan_hoi_hop_le()),
        ],
    )

    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat(vlm_retries=2))

    assert ket_qua.ok
    assert client.so_lan_goi == 2


# ---------------------------------------------------------------------------
# Tụt cấp json_mode khi endpoint không hỗ trợ
# ---------------------------------------------------------------------------
def test_tut_tu_schema_xuong_object_khi_khong_ho_tro(monkeypatch):
    loi_schema = _loi_openai(openai.BadRequestError, "response_format is not supported for this model")
    _gan_client_gia(monkeypatch, [loi_schema, _KetQuaGia(_phan_hoi_hop_le())])

    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat(vlm_json_mode="schema"))

    assert ket_qua.ok


def test_loi_400_khong_lien_quan_response_format_thi_khong_tut_cap(monkeypatch):
    """Lỗi 400 vì lý do khác (vd ảnh hỏng) phải báo thẳng, không âm thầm thử
    chế độ JSON khác — thử lại vô ích chỉ tốn thời gian chờ."""
    loi_khac = _loi_openai(openai.BadRequestError, "image could not be decoded")
    _gan_client_gia(monkeypatch, [loi_khac])

    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat())

    assert not ket_qua.ok
    assert "bị từ chối" in ket_qua.error


# ---------------------------------------------------------------------------
# Lỗi cố định — không thử lại
# ---------------------------------------------------------------------------
def test_sai_api_key_bao_ro_khong_thu_lai(monkeypatch):
    loi = _loi_openai(openai.AuthenticationError, "invalid api key", status=401)
    client = _gan_client_gia(monkeypatch, [loi])

    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat())

    assert not ket_qua.ok
    assert "api key" in ket_qua.error.lower()
    assert client.so_lan_goi == 1, "lỗi xác thực là lỗi cố định, thử lại vô ích"


def test_sai_ten_model_bao_ro(monkeypatch):
    loi = _loi_openai(openai.NotFoundError, "model not found", status=404)
    _gan_client_gia(monkeypatch, [loi])

    ket_qua = dem_thuoc_trong_anh(ANH_GIA, settings=_cai_dat(vlm_model="mo-hinh-khong-ton-tai"))

    assert not ket_qua.ok
    assert "mo-hinh-khong-ton-tai" in ket_qua.error


# ---------------------------------------------------------------------------
# Model trả về JSON méo
# ---------------------------------------------------------------------------
def test_model_tra_ve_khong_phai_json_thi_bao_loi_ro():
    from backend.services.photo_verification.vlm_bridge import _extract_json

    with pytest.raises(ValueError):
        _extract_json("tôi không tìm thấy thuốc nào trong ảnh này")


def test_json_boc_duoc_tu_trong_khoi_markdown():
    from backend.services.photo_verification.vlm_bridge import _extract_json

    text = '```json\n{"vien_nen": 2}\n```'
    assert _extract_json(text) == {"vien_nen": 2}


def test_gia_tri_am_bi_ep_ve_khong():
    from backend.services.photo_verification.vlm_bridge import _coerce

    counts, _, _, _ = _coerce({"vien_nen": -5})
    assert counts["vien_nen"] == 0
