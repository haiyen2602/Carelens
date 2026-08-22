"""VlmTelemetryService (backend/services/vlm_telemetry.py) - khong can key
Langfuse that: SDK Langfuse bi mock hoan toan, chi kiem chung logic
is_langfuse_connected() phan anh dung ket qua init (thanh cong/that
bai/khong cau hinh), khac han "co set bien moi truong hay khong"."""

from unittest.mock import MagicMock, patch

from backend.config import Settings
from backend.services.vlm_telemetry import VlmTelemetryService


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


def test_khong_cau_hinh_key_thi_chua_ket_noi():
    # Ep rong TUONG MINH - khong dua vao gia tri mac dinh cua Settings(), vi
    # .env that cua may dev co the da co key VLM_LANGFUSE_* that (nguoi dung
    # tu cau hinh de dung tinh nang), lam test nay false-fail neu chi doc mac
    # dinh.
    settings = _settings(vlm_langfuse_public_key="", vlm_langfuse_secret_key="")
    with patch("backend.services.vlm_telemetry.get_settings", return_value=settings):
        service = VlmTelemetryService()
    assert service.is_langfuse_connected() is False


def test_co_key_hop_le_thi_ket_noi_thanh_cong():
    settings = _settings(vlm_langfuse_public_key="pk-lf-test", vlm_langfuse_secret_key="sk-lf-test")
    fake_client = MagicMock()
    with (
        patch("backend.services.vlm_telemetry.get_settings", return_value=settings),
        patch("langfuse.Langfuse", return_value=fake_client) as mock_langfuse,
    ):
        service = VlmTelemetryService()

    assert service.is_langfuse_connected() is True
    mock_langfuse.assert_called_once_with(
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        host=settings.vlm_langfuse_host,
    )


def test_langfuse_constructor_loi_thi_khong_ket_noi():
    settings = _settings(vlm_langfuse_public_key="pk-lf-test", vlm_langfuse_secret_key="sk-lf-test")
    with (
        patch("backend.services.vlm_telemetry.get_settings", return_value=settings),
        patch("langfuse.Langfuse", side_effect=RuntimeError("host unreachable")),
    ):
        service = VlmTelemetryService()

    assert service.is_langfuse_connected() is False
