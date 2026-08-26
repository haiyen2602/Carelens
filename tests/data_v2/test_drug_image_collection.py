"""Deterministic B-02 coverage with local image bytes and no external HTTP."""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "data_v2"))

from drug_image_collection import (  # noqa: E402
    ImageRecord,
    SourceCandidate,
    collect,
    extract_primary_image_url,
    load_source_candidates,
    validate_image_bytes,
)


def candidate(*, product_id: str = "product-1", url: str = "https://cdn.nhathuoclongchau.com.vn/a.jpg") -> SourceCandidate:
    return SourceCandidate(
        drug_product_id=product_id,
        legacy_drug_id=f"legacy-{product_id}",
        source_product_id="sku-1",
        source_snapshot_id=f"snapshot-{product_id}",
        source_page_url="https://nhathuoclongchau.com.vn/thuoc/a.html",
        original_image_url=url,
        source_content_hash="source-hash",
        parser_version="test-parser",
        source="nhathuoclongchau",
    )


def image_bytes(*, color: str = "blue") -> bytes:
    image = Image.effect_noise((256, 192), 75).convert("RGB")
    if color != "blue":
        image.paste(Image.new("RGB", image.size, color=color))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class FakeDownloader:
    def __init__(self, responses: dict[str, tuple[bytes | None, str | None, str | None]]) -> None:
        self.responses = responses
        self.requests: list[str] = []

    def fetch(self, url: str) -> tuple[bytes | None, str | None, str | None]:
        self.requests.append(url)
        return self.responses[url]


def test_primary_image_prefers_declared_product_image() -> None:
    data = {
        "props": {
            "pageProps": {
                "product": {"primaryImage": {"url": "https://cdn.nhathuoclongchau.com.vn/primary.jpg"}},
                "transformedProductData": {"galleryImgUrls": [{"url": "https://cdn.nhathuoclongchau.com.vn/gallery.jpg"}]},
            }
        }
    }
    assert extract_primary_image_url(data) == ("https://cdn.nhathuoclongchau.com.vn/primary.jpg", "product.primaryImage")


def test_primary_image_uses_product_gallery_not_page_chrome() -> None:
    data = {"props": {"pageProps": {"product": {}, "transformedProductData": {"galleryImgUrls": [{"url": "https://cdn.nhathuoclongchau.com.vn/gallery.jpg"}]}}}}
    assert extract_primary_image_url(data) == ("https://cdn.nhathuoclongchau.com.vn/gallery.jpg", "transformedProductData.galleryImgUrls[0]")


def test_html_disguised_as_image_is_rejected() -> None:
    image, mime_type, reason = validate_image_bytes(b"<html>not an image</html>" * 100, "image/jpeg")
    assert image is None
    assert mime_type == "image/jpeg"
    assert reason == "CORRUPT_IMAGE"


def test_collection_deduplicates_url_and_records_checksum_review(tmp_path: Path) -> None:
    url = "https://cdn.nhathuoclongchau.com.vn/shared.jpg"
    payload = image_bytes()
    downloader = FakeDownloader({url: (payload, "image/png", None)})
    records, queues, stats = collect(
        [candidate(product_id="product-1", url=url), candidate(product_id="product-2", url=url)],
        output_dir=tmp_path,
        allow_source_download=True,
        source_rights_status="APPROVED",
        downloader=downloader,  # type: ignore[arg-type]
    )
    assert downloader.requests == [url]
    assert stats["DUPLICATE_URL"] == 1
    assert stats["DUPLICATE_CHECKSUM"] == 1
    assert all(record.validation_status == "VALIDATED" for record in records)
    assert records[1].duplicate_url_of == records[0].image_record_id
    assert records[1].duplicate_checksum_of == records[0].image_record_id
    assert any(item.reason_code == "DUPLICATE_REVIEW" for item in queues)


def test_resume_does_not_download_a_valid_existing_image(tmp_path: Path) -> None:
    item = candidate()
    payload = image_bytes()
    first = FakeDownloader({item.original_image_url: (payload, "image/png", None)})
    collect([item], output_dir=tmp_path, allow_source_download=True, source_rights_status="APPROVED", downloader=first)  # type: ignore[arg-type]
    second = FakeDownloader({item.original_image_url: (None, None, "HTTP_FAILURE")})
    records, _queues, stats = collect([item], output_dir=tmp_path, allow_source_download=True, source_rights_status="APPROVED", resume=True, downloader=second)  # type: ignore[arg-type]
    assert second.requests == []
    assert stats["RESUMED"] == 1
    assert records[0].validation_status == "VALIDATED"


def test_failed_record_retries_only_when_requested(tmp_path: Path) -> None:
    item = candidate()
    failed = FakeDownloader({item.original_image_url: (None, None, "HTTP_FAILURE")})
    collect([item], output_dir=tmp_path, allow_source_download=True, source_rights_status="APPROVED", downloader=failed)  # type: ignore[arg-type]
    skipped = FakeDownloader({item.original_image_url: (image_bytes(), "image/png", None)})
    records, queues, stats = collect([item], output_dir=tmp_path, allow_source_download=True, source_rights_status="APPROVED", resume=True, downloader=skipped)  # type: ignore[arg-type]
    assert skipped.requests == []
    assert stats["SKIPPED_FAILED"] == 1
    assert [queue.reason_code for queue in queues] == ["DOWNLOAD_FAILED"]
    retried = FakeDownloader({item.original_image_url: (image_bytes(), "image/png", None)})
    records, _queues, stats = collect([item], output_dir=tmp_path, allow_source_download=True, source_rights_status="APPROVED", resume=True, retry_failed=True, downloader=retried)  # type: ignore[arg-type]
    assert retried.requests == [item.original_image_url]
    assert stats["VALIDATED"] == 1
    assert records[0].validation_status == "VALIDATED"


def test_dry_run_never_uses_downloader_and_marks_rights_review(tmp_path: Path) -> None:
    item = candidate()
    downloader = FakeDownloader({item.original_image_url: (image_bytes(), "image/png", None)})
    records, _queues, stats = collect([item], output_dir=tmp_path, allow_source_download=False, source_rights_status=None, downloader=downloader)  # type: ignore[arg-type]
    assert downloader.requests == []
    assert stats["PLANNED"] == 1
    assert records[0].validation_reason == "SOURCE_RIGHTS_REVIEW_REQUIRED"


def test_dry_run_resume_keeps_one_planned_record(tmp_path: Path) -> None:
    item = candidate()
    collect([item], output_dir=tmp_path, allow_source_download=False, source_rights_status=None)
    records, _queues, stats = collect(
        [item], output_dir=tmp_path, allow_source_download=False, source_rights_status=None, resume=True
    )
    assert len(records) == 1
    assert stats["RESUMED_PLANNED"] == 1


def test_known_placeholder_url_is_rejected_without_downloading(tmp_path: Path) -> None:
    item = candidate()
    downloader = FakeDownloader({item.original_image_url: (image_bytes(), "image/png", None)})
    records, queues, stats = collect(
        [item],
        output_dir=tmp_path,
        allow_source_download=True,
        source_rights_status="APPROVED",
        downloader=downloader,  # type: ignore[arg-type]
        known_placeholder_urls={item.original_image_url},
    )
    assert downloader.requests == []
    assert stats["PLACEHOLDER_REJECTED"] == 1
    assert records[0].validation_reason == "KNOWN_PLACEHOLDER_URL"
    assert queues[0].reason_code == "INVALID_IMAGE"


def test_download_requires_explicit_rights_approval(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="source download requires"):
        collect([candidate()], output_dir=tmp_path, allow_source_download=True, source_rights_status=None)


def test_normalized_checksum_matches_persisted_derivative(tmp_path: Path) -> None:
    item = candidate()
    payload = image_bytes()
    downloader = FakeDownloader({item.original_image_url: (payload, "image/png", None)})
    records, _queues, _stats = collect([item], output_dir=tmp_path, allow_source_download=True, source_rights_status="APPROVED", downloader=downloader)  # type: ignore[arg-type]
    record: ImageRecord = records[0]
    assert hashlib.sha256((tmp_path / str(record.storage_relative_path)).read_bytes()).hexdigest() == record.normalized_checksum_sha256
    assert set(record.__dataclass_fields__) <= set(record.__dict__)
    assert record.storage_relative_path == "images/product-1/primary.webp"


def test_frozen_catalog_maps_only_b02_eligible_products() -> None:
    candidates, queues = load_source_candidates()
    legacy_ids = {item.legacy_drug_id for item in candidates}
    assert len(candidates) == 3545
    assert "bisoprolol-stada-5mg-3x10" not in legacy_ids
    assert {item.reason_code for item in queues} == {"SOURCE_REDISCOVERY", "SOURCE_REVIEW"}
    assert sum(item.reason_code == "SOURCE_REDISCOVERY" for item in queues) == 9
    assert sum(item.reason_code == "SOURCE_REVIEW" for item in queues) == 2
