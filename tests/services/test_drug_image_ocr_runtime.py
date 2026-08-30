"""Fix_drug_OCR.md section 14: OCR runtime failure-mode coverage.

`OptionalTesseractOcrExtractor` must fail closed and bounded (never raise
into the caller) for every one of: pytesseract not importable, the
tesseract binary not on PATH, a required language pack missing, the
runtime probe itself erroring, a per-call timeout, and a mid-call process
failure. It must also succeed and report `OCR_AVAILABLE` when everything
is genuinely present, and must not re-probe once a runtime is confirmed
available (init cost is paid once, not per image).

PR #166 follow-up: `extract()` now runs Tesseract TWICE per image (once
on the color image as given, once on its grayscale conversion) and
unions both text outputs -- a real production finding (verified against
real photos, not a guess) that Tesseract's own color-image binarization
badly garbles some real box text a plain grayscale conversion reads
correctly, while grayscale-only regressed a different, already-working
real photo. Every fixture/assertion below that counted exactly one
`image_to_string` call per `extract()` call now expects two.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from PIL import Image

os.environ["INTERNAL_AUTH_SECRET"] = "b05-local-test-secret"
os.environ["JWT_SECRET"] = "b05-local-test-jwt"

from backend.services import drug_image_recognition as recognition_module
from backend.services.drug_image_recognition import (
    OCR_AVAILABLE,
    OCR_FAILED,
    OCR_UNAVAILABLE,
    OptionalTesseractOcrExtractor,
)


def _image() -> Image.Image:
    return Image.new("RGB", (64, 64), "white")


class _FakeTesseractError(Exception):
    pass


class _FakeTesseractNotFoundError(Exception):
    pass


class _FakePytesseractModule:
    """Stand-in for the real `pytesseract` module, one flag per scenario."""

    def __init__(
        self,
        *,
        languages: frozenset[str] | None = frozenset({"eng", "vie"}),
        get_languages_raises: Exception | None = None,
        image_to_string_result: str | Callable[[Image.Image], str] = "SNAPCEF",
        image_to_string_raises: Exception | None = None,
        binary_present: bool = True,
    ) -> None:
        self._languages = languages
        self._get_languages_raises = get_languages_raises
        self._image_to_string_result = image_to_string_result
        self._image_to_string_raises = image_to_string_raises
        self.binary_present = binary_present
        self.image_to_string_calls: list[float] = []
        self.image_to_string_modes: list[str] = []

        self.TesseractError = _FakeTesseractError
        self.TesseractNotFoundError = _FakeTesseractNotFoundError
        self.pytesseract = self  # mirrors pytesseract.pytesseract.tesseract_cmd
        self.tesseract_cmd = "tesseract"

    def get_languages(self, config: str = "") -> frozenset[str]:  # noqa: ARG002
        if self._get_languages_raises is not None:
            raise self._get_languages_raises
        assert self._languages is not None
        return self._languages

    def image_to_string(self, image: Image.Image, *, lang: str, timeout: float) -> str:  # noqa: ARG002
        self.image_to_string_calls.append(timeout)
        self.image_to_string_modes.append(image.mode)
        if self._image_to_string_raises is not None:
            raise self._image_to_string_raises
        if callable(self._image_to_string_result):
            return self._image_to_string_result(image)
        return self._image_to_string_result


def _patch_which(monkeypatch, present: bool) -> None:
    monkeypatch.setattr(recognition_module.shutil, "which", lambda _cmd: ("/usr/bin/tesseract" if present else None))


def test_pytesseract_not_importable_reports_ocr_unavailable(monkeypatch) -> None:
    def _raise_import_error() -> None:
        raise ImportError("no module named pytesseract")

    monkeypatch.setattr(recognition_module, "_load_pytesseract", _raise_import_error)
    observation = OptionalTesseractOcrExtractor().extract(_image())
    assert observation.status == OCR_UNAVAILABLE
    assert observation.text == ""


def test_tesseract_binary_missing_from_path_reports_ocr_unavailable(monkeypatch) -> None:
    fake = _FakePytesseractModule()
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=False)
    observation = OptionalTesseractOcrExtractor().extract(_image())
    assert observation.status == OCR_UNAVAILABLE
    assert fake.image_to_string_calls == []  # never attempted a call without a binary


def test_missing_vietnamese_language_pack_reports_ocr_unavailable(monkeypatch) -> None:
    fake = _FakePytesseractModule(languages=frozenset({"eng"}))  # vie absent
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    observation = OptionalTesseractOcrExtractor(languages="vie+eng").extract(_image())
    assert observation.status == OCR_UNAVAILABLE
    assert fake.image_to_string_calls == []


def test_runtime_probe_error_reports_ocr_failed_not_unavailable(monkeypatch) -> None:
    fake = _FakePytesseractModule(get_languages_raises=OSError("tesseract crashed during probe"))
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    observation = OptionalTesseractOcrExtractor().extract(_image())
    assert observation.status == OCR_FAILED


def test_probe_tesseract_not_found_mid_check_reports_ocr_unavailable(monkeypatch) -> None:
    fake = _FakePytesseractModule(get_languages_raises=_FakeTesseractNotFoundError())
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    observation = OptionalTesseractOcrExtractor().extract(_image())
    assert observation.status == OCR_UNAVAILABLE


def test_call_timeout_reports_ocr_failed_and_does_not_raise(monkeypatch) -> None:
    fake = _FakePytesseractModule(image_to_string_raises=RuntimeError("tesseract timed out"))
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    observation = OptionalTesseractOcrExtractor(timeout_seconds=0.01).extract(_image())
    assert observation.status == OCR_FAILED
    assert observation.text == ""
    # Both the color and grayscale passes are attempted and both fail here.
    assert fake.image_to_string_calls == [0.01, 0.01]


def test_one_pass_failing_does_not_lose_the_other_passs_text(monkeypatch) -> None:
    """If the color pass crashes but the grayscale pass still succeeds
    (or vice versa), the surviving pass's text must still reach the
    caller -- one failed pass must not discard real signal the other
    pass found."""

    def _fail_on_color_only(image: Image.Image) -> str:
        if image.mode != "L":
            raise _FakeTesseractError("color pass crashed")
        return "LONG HUYET PH"

    fake = _FakePytesseractModule(image_to_string_result=_fail_on_color_only)
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    observation = OptionalTesseractOcrExtractor().extract(_image())
    assert observation.status == OCR_AVAILABLE
    assert observation.text == "LONG HUYET PH"
    assert fake.image_to_string_modes == ["RGB", "L"]


def test_process_failure_mid_call_reports_ocr_failed(monkeypatch) -> None:
    fake = _FakePytesseractModule(image_to_string_raises=_FakeTesseractError("engine crashed"))
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    observation = OptionalTesseractOcrExtractor().extract(_image())
    assert observation.status == OCR_FAILED


def test_tesseract_removed_mid_call_resets_runtime_and_reports_unavailable(monkeypatch) -> None:
    fake = _FakePytesseractModule(image_to_string_raises=_FakeTesseractNotFoundError())
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    extractor = OptionalTesseractOcrExtractor()
    first = extractor.extract(_image())
    assert first.status == OCR_UNAVAILABLE
    # A resolved-but-then-vanished binary must not be trusted as available
    # on the next call either -- confirms the runtime cache was cleared.
    assert extractor._runtime is None  # noqa: SLF001 - white-box regression on the reset path


def test_genuinely_available_runtime_extracts_text_once_probed(monkeypatch) -> None:
    fake = _FakePytesseractModule(image_to_string_result="SNAPCEF 16mg/10ml")
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    extractor = OptionalTesseractOcrExtractor(timeout_seconds=7.5)
    observation = extractor.extract(_image())
    assert observation.status == OCR_AVAILABLE
    # Union of the color pass and the grayscale pass -- the fake returns
    # the same canned text either way here, so it appears twice.
    assert observation.text == "SNAPCEF 16mg/10ml\nSNAPCEF 16mg/10ml"
    assert fake.image_to_string_calls == [7.5, 7.5]
    assert fake.image_to_string_modes == ["RGB", "L"]


def test_union_captures_text_the_other_pass_alone_would_have_missed(monkeypatch) -> None:
    """Direct regression test for the real production finding: the color
    pass and the grayscale pass can each recover DIFFERENT real text from
    the same photo -- the union must keep both, not just one."""

    def _mode_dependent_text(image: Image.Image) -> str:
        return "SNAPCEF 16mg" if image.mode != "L" else "LONG HUYET PH"

    fake = _FakePytesseractModule(image_to_string_result=_mode_dependent_text)
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    observation = OptionalTesseractOcrExtractor().extract(_image())
    assert observation.status == OCR_AVAILABLE
    assert "SNAPCEF 16mg" in observation.text
    assert "LONG HUYET PH" in observation.text


def test_available_runtime_is_probed_once_not_per_image(monkeypatch) -> None:
    probe_calls = {"count": 0}
    fake = _FakePytesseractModule()
    real_get_languages = fake.get_languages

    def _counting_get_languages(config: str = "") -> frozenset[str]:
        probe_calls["count"] += 1
        return real_get_languages(config)

    fake.get_languages = _counting_get_languages
    monkeypatch.setattr(recognition_module, "_load_pytesseract", lambda: fake)
    _patch_which(monkeypatch, present=True)
    extractor = OptionalTesseractOcrExtractor()
    extractor.extract(_image())
    extractor.extract(_image())
    extractor.extract(_image())
    assert probe_calls["count"] == 1
    # Two Tesseract calls (color + grayscale) per extract() call.
    assert len(fake.image_to_string_calls) == 6


def test_negative_timeout_rejected_at_construction() -> None:
    try:
        OptionalTesseractOcrExtractor(timeout_seconds=0)
    except ValueError:
        pass
    else:
        raise AssertionError("zero/negative timeout must be rejected eagerly, not at call time")
