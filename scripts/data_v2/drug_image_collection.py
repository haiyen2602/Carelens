"""Build a resumable, offline reference-image collection artifact for B-02.

This module deliberately has no database dependency.  It turns the frozen
Canonical V2 promotion decisions and their raw Long Chau snapshots into a
validated local artifact that B-03 may later import into durable storage.
Network downloads are opt-in and additionally require recorded source-rights
approval; a normal run is therefore safe to use as a dry-run/source audit.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "drug-images" / "v1"
FINAL_CANONICAL_DIR = ROOT / "data pharmacy" / "v2" / "final_canonical"
FULL_RECRAWL_RAW_DIR = ROOT / "data pharmacy" / "v2" / "full_recrawl" / "raw_snapshots" / "nhathuoclongchau"
TARGETED_FRESH_RAW_DIR = FINAL_CANONICAL_DIR / "targeted_fresh" / "raw_snapshots" / "nhathuoclongchau"

COLLECTION_VERSION = "drug-image-b02-v1"
NORMALIZED_FORMAT = "webp"
PARSER_VERSION = "longchau-v2.1.0"
IMAGE_RECORD_NAMESPACE = uuid.UUID("11d6b3a9-f39b-4a8e-b994-30a714debe65")
MIN_IMAGE_BYTES = 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MIN_IMAGE_DIMENSION = 64
MAX_NORMALIZED_DIMENSION = 1600
MIN_ASPECT_RATIO = 0.1
MAX_ASPECT_RATIO = 10.0
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
DEFAULT_RATE_LIMIT_SECONDS = 1.0
USER_AGENT = "VMEC-04-DrugImageCollector/1.0 (internal offline dataset)"
LOCK_FILENAME = ".drug-image-collection.lock"
_ACTIVE_OUTPUT_LOCKS: set[Path] = set()
_ACTIVE_OUTPUT_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class SourceCandidate:
    """One source-linked product eligible for primary-image collection."""

    drug_product_id: str
    legacy_drug_id: str
    source_product_id: str | None
    source_snapshot_id: str
    source_page_url: str
    original_image_url: str
    source_content_hash: str | None
    parser_version: str
    source: str


@dataclass(frozen=True)
class QueueItem:
    """A durable, machine-readable reason why a product was not collected."""

    drug_product_id: str | None
    legacy_drug_id: str
    source: str
    reason_code: str
    detail: str
    retryable: bool
    timestamp: str


@dataclass(frozen=True)
class ImageRecord:
    """Offline B-02 metadata contract; this is not a runtime DB DTO."""

    image_record_id: str
    drug_product_id: str
    legacy_drug_id: str
    source_product_id: str | None
    source_snapshot_id: str
    source_page_url: str
    original_image_url: str
    retrieved_at: str
    source_content_hash: str | None
    image_checksum_sha256: str | None
    normalized_checksum_sha256: str | None
    mime_type: str | None
    width: int | None
    height: int | None
    file_size: int | None
    normalized_format: str
    storage_relative_path: str | None
    view_type: str
    is_primary: bool
    validation_status: str
    validation_reason: str | None
    parser_version: str
    collection_version: str
    duplicate_url_of: str | None = None
    duplicate_checksum_of: str | None = None


def utc_now() -> str:
    """Return an explicit UTC timestamp for artifact provenance."""

    return datetime.now(UTC).isoformat()


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """Yield JSON objects without changing source artifacts."""

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid JSONL at {path}:{line_number}") from error


def unique_temporary_path(path: Path) -> Path:
    """Create a same-directory temporary path that cannot collide with another writer."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    return Path(temporary_name)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Atomically write a deterministic JSONL artifact with one row per record."""

    temporary_path = unique_temporary_path(path)
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def write_text_atomically(path: Path, content: str) -> None:
    """Replace one text artifact without exposing a partial file to a reader."""

    temporary_path = unique_temporary_path(path)
    try:
        temporary_path.write_text(content, encoding="utf-8", newline="\n")
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def copy_file_atomically(source: Path, target: Path) -> None:
    """Copy a persisted derivative without retaining its bytes in Python memory."""

    temporary_path = unique_temporary_path(target)
    try:
        shutil.copyfile(source, temporary_path)
        temporary_path.replace(target)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


class OutputDirectoryBusyError(RuntimeError):
    """Raised when another B-02 collector owns an output artifact directory."""


@contextmanager
def output_directory_lock(output_dir: Path) -> Iterator[None]:
    """Fail fast unless this process is the sole writer for ``output_dir``.

    The marker can remain after a crash: operating-system byte-range locks are
    released automatically when the owning process exits, so it is not a stale
    lock condition. The in-process guard also makes accidental re-entry fail.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = (output_dir / LOCK_FILENAME).resolve()
    with _ACTIVE_OUTPUT_LOCKS_GUARD:
        if lock_path in _ACTIVE_OUTPUT_LOCKS:
            raise OutputDirectoryBusyError(f"another collector already owns {output_dir}")
        _ACTIVE_OUTPUT_LOCKS.add(lock_path)

    handle = None
    try:
        handle = lock_path.open("a+b")
        if lock_path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise OutputDirectoryBusyError(f"another collector already owns {output_dir}") from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        if handle is not None:
            handle.close()
        with _ACTIVE_OUTPUT_LOCKS_GUARD:
            _ACTIVE_OUTPUT_LOCKS.discard(lock_path)


def image_record_id(candidate: SourceCandidate) -> str:
    """Create a stable ID from product identity and image provenance."""

    key = f"{candidate.drug_product_id}:{candidate.source_snapshot_id}:{candidate.original_image_url}"
    return str(uuid.uuid5(IMAGE_RECORD_NAMESPACE, key))


def source_snapshot_path(snapshot_id: str) -> Path | None:
    """Resolve only known frozen snapshot roots, never a name-based search."""

    for root in (FULL_RECRAWL_RAW_DIR, TARGETED_FRESH_RAW_DIR):
        candidate = root / f"{snapshot_id}.json"
        if candidate.exists():
            return candidate
    return None


def value_url(value: Any) -> str | None:
    """Read a source URL only from an explicit source image value."""

    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def extract_primary_image_url(raw_next_data: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract the product's declared primary image, with gallery fallback.

    The fallback is limited to the product gallery.  It does not recursively
    inspect page chrome, recommendations, logos, or banners.
    """

    page_props = (raw_next_data.get("props") or {}).get("pageProps") or {}
    product = page_props.get("product") or {}
    url = value_url(product.get("primaryImage"))
    if url:
        return url, "product.primaryImage"

    gallery = (page_props.get("transformedProductData") or {}).get("galleryImgUrls") or []
    if gallery:
        url = value_url(gallery[0])
        if url:
            return url, "transformedProductData.galleryImgUrls[0]"
    return None, None


def queue_item(
    *,
    drug_product_id: str | None,
    legacy_drug_id: str,
    source: str,
    reason_code: str,
    detail: str,
    retryable: bool,
) -> QueueItem:
    """Construct one failure/review queue item without losing its reason."""

    return QueueItem(
        drug_product_id=drug_product_id,
        legacy_drug_id=legacy_drug_id,
        source=source,
        reason_code=reason_code,
        detail=detail,
        retryable=retryable,
        timestamp=utc_now(),
    )


def load_source_candidates(
    *,
    canonical_dir: Path = FINAL_CANONICAL_DIR,
) -> tuple[list[SourceCandidate], list[QueueItem]]:
    """Map canonical products to frozen snapshots and declared primary URLs.

    Only ``PROMOTED_FRESH`` active records are eligible.  ``KEEP_LEGACY``
    records become ``SOURCE_REDISCOVERY``; malformed/missing source payloads
    become ``SOURCE_REVIEW``.  This preserves the B-01 boundaries.
    """

    products = {str(row["legacy_drug_id"]): str(row["id"]) for row in read_jsonl(canonical_dir / "drug_product.jsonl")}
    candidates: list[SourceCandidate] = []
    queues: list[QueueItem] = []

    for decision in read_jsonl(canonical_dir / "final_promotion_decisions.jsonl"):
        legacy_drug_id = str(decision.get("legacy_drug_id") or "")
        if not legacy_drug_id:
            continue
        if decision.get("terminal_decision") == "EXCLUDE_ACTIVE_CORPUS":
            continue
        product_id = products.get(legacy_drug_id)
        terminal = str(decision.get("terminal_decision") or "")
        if terminal == "KEEP_LEGACY":
            queues.append(
                queue_item(
                    drug_product_id=product_id,
                    legacy_drug_id=legacy_drug_id,
                    source="nhathuoclongchau",
                    reason_code="SOURCE_REDISCOVERY",
                    detail="canonical decision is KEEP_LEGACY; no name-based replacement is allowed",
                    retryable=False,
                )
            )
            continue
        if terminal != "PROMOTED_FRESH" or not decision.get("active"):
            continue
        if not product_id:
            queues.append(
                queue_item(
                    drug_product_id=None,
                    legacy_drug_id=legacy_drug_id,
                    source="nhathuoclongchau",
                    reason_code="SOURCE_REVIEW",
                    detail="promoted source record has no active canonical product mapping",
                    retryable=False,
                )
            )
            continue
        snapshot_id = str(decision.get("snapshot_id") or "")
        snapshot_path = source_snapshot_path(snapshot_id)
        if not snapshot_id or not snapshot_path:
            queues.append(
                queue_item(
                    drug_product_id=product_id,
                    legacy_drug_id=legacy_drug_id,
                    source="nhathuoclongchau",
                    reason_code="SOURCE_REVIEW",
                    detail="promoted record does not have a resolvable frozen source snapshot",
                    retryable=False,
                )
            )
            continue
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        raw_next_data = snapshot.get("raw_next_data")
        if not isinstance(raw_next_data, dict):
            queues.append(
                queue_item(
                    drug_product_id=product_id,
                    legacy_drug_id=legacy_drug_id,
                    source=str(snapshot.get("source") or "nhathuoclongchau"),
                    reason_code="SOURCE_REVIEW",
                    detail="snapshot has no parseable raw_next_data object",
                    retryable=False,
                )
            )
            continue
        url, _origin = extract_primary_image_url(raw_next_data)
        product = ((raw_next_data.get("props") or {}).get("pageProps") or {}).get("product") or {}
        if not url:
            queues.append(
                queue_item(
                    drug_product_id=product_id,
                    legacy_drug_id=legacy_drug_id,
                    source=str(snapshot.get("source") or "nhathuoclongchau"),
                    reason_code="SOURCE_REVIEW",
                    detail="snapshot product has no declared primary image URL",
                    retryable=False,
                )
            )
            continue
        candidates.append(
            SourceCandidate(
                drug_product_id=product_id,
                legacy_drug_id=legacy_drug_id,
                source_product_id=str(product.get("sku")) if product.get("sku") is not None else None,
                source_snapshot_id=str(snapshot.get("id") or snapshot_id),
                source_page_url=str(snapshot.get("source_url") or decision.get("source_url") or ""),
                original_image_url=url,
                source_content_hash=str(snapshot.get("content_hash")) if snapshot.get("content_hash") else None,
                parser_version=str(snapshot.get("parser_version") or decision.get("parser_version") or PARSER_VERSION),
                source=str(snapshot.get("source") or "nhathuoclongchau"),
            )
        )

    return sorted(candidates, key=lambda item: (item.drug_product_id, item.original_image_url)), queues


def validate_source_url(url: str, expected_host_suffix: str = "nhathuoclongchau.com.vn") -> str | None:
    """Reject malformed or off-source image URLs before any request is made."""

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return "URL_SCHEME_NOT_HTTPS"
    if not host or not (host == expected_host_suffix or host.endswith(f".{expected_host_suffix}")):
        return "URL_HOST_NOT_ALLOWED"
    if not parsed.path:
        return "URL_PATH_MISSING"
    return None


def validate_image_bytes(content: bytes, content_type: str | None) -> tuple[Image.Image | None, str | None, str | None]:
    """Decode an image and return a normalized RGB source image or a reason."""

    mime_type = (content_type or "").split(";", 1)[0].strip().lower()
    if not mime_type.startswith("image/"):
        return None, mime_type or None, "INVALID_CONTENT_TYPE"
    if len(content) < MIN_IMAGE_BYTES:
        return None, mime_type, "IMAGE_TOO_SMALL"
    if len(content) > MAX_IMAGE_BYTES:
        return None, mime_type, "IMAGE_TOO_LARGE"
    try:
        with Image.open(io.BytesIO(content)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(content)) as decoded:
            image = ImageOps.exif_transpose(decoded).convert("RGB")
            image.load()
    except (OSError, UnidentifiedImageError, ValueError):
        return None, mime_type, "CORRUPT_IMAGE"
    width, height = image.size
    if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
        return None, mime_type, "IMAGE_DIMENSIONS_TOO_SMALL"
    aspect_ratio = width / height
    if not MIN_ASPECT_RATIO <= aspect_ratio <= MAX_ASPECT_RATIO:
        return None, mime_type, "IMAGE_ASPECT_RATIO_OUT_OF_RANGE"
    return image, mime_type, None


def normalize_image(image: Image.Image) -> bytes:
    """Correct orientation and downscale only; never crop or upscale."""

    normalized = image.copy()
    normalized.thumbnail((MAX_NORMALIZED_DIMENSION, MAX_NORMALIZED_DIMENSION))
    output = io.BytesIO()
    normalized.save(output, format="WEBP", quality=85, method=6)
    return output.getvalue()


class RequestsImageDownloader:
    """Small, rate-limited HTTP client for an explicitly approved collection."""

    def __init__(self, rate_limit_seconds: float = DEFAULT_RATE_LIMIT_SECONDS) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
        self._rate_limit_seconds = rate_limit_seconds
        self._last_request_at = 0.0

    def fetch(self, url: str) -> tuple[bytes | None, str | None, str | None]:
        """Return bytes/content type or a stable retryable failure reason."""

        for attempt in range(MAX_RETRIES):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self._rate_limit_seconds:
                time.sleep(self._rate_limit_seconds - elapsed)
            try:
                response = self._session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, stream=True)
                self._last_request_at = time.monotonic()
                if response.status_code != 200:
                    if response.status_code >= 500 and attempt + 1 < MAX_RETRIES:
                        time.sleep(2**attempt)
                        continue
                    return None, None, f"HTTP_{response.status_code}"
                declared_length = response.headers.get("Content-Length")
                if declared_length and int(declared_length) > MAX_IMAGE_BYTES:
                    return None, response.headers.get("Content-Type"), "IMAGE_TOO_LARGE"
                content = response.content
                return content, response.headers.get("Content-Type"), None
            except requests.Timeout:
                if attempt + 1 < MAX_RETRIES:
                    time.sleep(2**attempt)
                    continue
                return None, None, "TIMEOUT"
            except requests.RequestException:
                if attempt + 1 < MAX_RETRIES:
                    time.sleep(2**attempt)
                    continue
                return None, None, "HTTP_FAILURE"
        return None, None, "HTTP_FAILURE"


def load_existing_records(manifest_path: Path) -> dict[str, ImageRecord]:
    """Load the latest row per stable record ID for resume/idempotency."""

    if not manifest_path.exists():
        return {}
    rows = (ImageRecord(**row) for row in read_jsonl(manifest_path))
    return {row.image_record_id: row for row in rows}


def load_existing_queues(queue_path: Path) -> list[QueueItem]:
    """Keep prior structured failures visible across a resume-only rerun."""

    if not queue_path.exists():
        return []
    return [QueueItem(**row) for row in read_jsonl(queue_path)]


def valid_existing_record(record: ImageRecord, output_dir: Path) -> bool:
    """Accept an existing record only when its local derivative still verifies."""

    if record.validation_status != "VALIDATED" or not record.storage_relative_path:
        return False
    path = output_dir / record.storage_relative_path
    return path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == record.normalized_checksum_sha256


def make_record(
    candidate: SourceCandidate,
    *,
    retrieved_at: str,
    status: str,
    reason: str | None,
    mime_type: str | None = None,
    checksum: str | None = None,
    normalized_checksum: str | None = None,
    width: int | None = None,
    height: int | None = None,
    file_size: int | None = None,
    storage_relative_path: str | None = None,
    duplicate_url_of: str | None = None,
    duplicate_checksum_of: str | None = None,
) -> ImageRecord:
    """Populate every B-02 contract field for success and failure rows."""

    return ImageRecord(
        image_record_id=image_record_id(candidate),
        drug_product_id=candidate.drug_product_id,
        legacy_drug_id=candidate.legacy_drug_id,
        source_product_id=candidate.source_product_id,
        source_snapshot_id=candidate.source_snapshot_id,
        source_page_url=candidate.source_page_url,
        original_image_url=candidate.original_image_url,
        retrieved_at=retrieved_at,
        source_content_hash=candidate.source_content_hash,
        image_checksum_sha256=checksum,
        normalized_checksum_sha256=normalized_checksum,
        mime_type=mime_type,
        width=width,
        height=height,
        file_size=file_size,
        normalized_format=NORMALIZED_FORMAT,
        storage_relative_path=storage_relative_path,
        view_type="front",
        is_primary=True,
        validation_status=status,
        validation_reason=reason,
        parser_version=candidate.parser_version,
        collection_version=COLLECTION_VERSION,
        duplicate_url_of=duplicate_url_of,
        duplicate_checksum_of=duplicate_checksum_of,
    )


def collect(
    candidates: list[SourceCandidate],
    *,
    output_dir: Path,
    allow_source_download: bool,
    source_rights_status: str | None,
    resume: bool = False,
    retry_failed: bool = False,
    downloader: RequestsImageDownloader | None = None,
    known_placeholder_urls: set[str] | None = None,
    known_placeholder_checksums: set[str] | None = None,
) -> tuple[list[ImageRecord], list[QueueItem], Counter[str]]:
    """Collect under an exclusive writer lock for the target artifact directory."""

    with output_directory_lock(output_dir):
        return _collect(
            candidates,
            output_dir=output_dir,
            allow_source_download=allow_source_download,
            source_rights_status=source_rights_status,
            resume=resume,
            retry_failed=retry_failed,
            downloader=downloader,
            known_placeholder_urls=known_placeholder_urls,
            known_placeholder_checksums=known_placeholder_checksums,
        )


def _collect(
    candidates: list[SourceCandidate],
    *,
    output_dir: Path,
    allow_source_download: bool,
    source_rights_status: str | None,
    resume: bool = False,
    retry_failed: bool = False,
    downloader: RequestsImageDownloader | None = None,
    known_placeholder_urls: set[str] | None = None,
    known_placeholder_checksums: set[str] | None = None,
) -> tuple[list[ImageRecord], list[QueueItem], Counter[str]]:
    """Collect validated derivatives, or create a safe offline dry-run plan."""

    if allow_source_download and source_rights_status != "APPROVED":
        raise PermissionError("source download requires --source-rights-status APPROVED")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.jsonl"
    failure_queue_path = output_dir / "failure_queues.jsonl"
    existing = load_existing_records(manifest_path) if resume or retry_failed else {}
    records = dict(existing)
    queues = load_existing_queues(failure_queue_path) if resume or retry_failed else []
    stats: Counter[str] = Counter(TOTAL_ELIGIBLE=len(candidates))
    first_by_url: dict[str, str] = {}
    first_by_checksum: dict[str, str] = {}
    processed_by_url: dict[str, ImageRecord] = {}
    downloader = downloader or RequestsImageDownloader()
    known_placeholder_urls = known_placeholder_urls or set()
    known_placeholder_checksums = known_placeholder_checksums or set()

    def checkpoint() -> None:
        ordered = [records[key] for key in sorted(records)]
        write_jsonl(manifest_path, (asdict(record) for record in ordered))
        write_jsonl(failure_queue_path, (asdict(item) for item in queues))

    def remember_processed_url(record: ImageRecord) -> None:
        """Keep lightweight result metadata only after content was received."""

        if record.image_checksum_sha256:
            processed_by_url.setdefault(record.original_image_url, record)

    def queue_invalid(
        candidate: SourceCandidate,
        reason: str,
        *,
        checksum: str | None = None,
        mime_type: str | None = None,
        file_size: int | None = None,
        duplicate_url_of: str | None = None,
    ) -> ImageRecord:
        record = make_record(
            candidate,
            retrieved_at=utc_now(),
            status="INVALID",
            reason=reason,
            mime_type=mime_type,
            checksum=checksum,
            file_size=file_size,
            duplicate_url_of=duplicate_url_of,
        )
        queues.append(
            queue_item(
                drug_product_id=candidate.drug_product_id,
                legacy_drug_id=candidate.legacy_drug_id,
                source=candidate.source,
                reason_code="INVALID_IMAGE",
                detail=reason,
                retryable=False,
            )
        )
        stats["INVALID_IMAGE"] += 1
        return record

    def queue_placeholder(
        candidate: SourceCandidate,
        reason: str,
        *,
        checksum: str | None = None,
        mime_type: str | None = None,
        file_size: int | None = None,
        duplicate_url_of: str | None = None,
    ) -> ImageRecord:
        record = make_record(
            candidate,
            retrieved_at=utc_now(),
            status="REJECTED",
            reason=reason,
            mime_type=mime_type,
            checksum=checksum,
            file_size=file_size,
            duplicate_url_of=duplicate_url_of,
        )
        queues.append(
            queue_item(
                drug_product_id=candidate.drug_product_id,
                legacy_drug_id=candidate.legacy_drug_id,
                source=candidate.source,
                reason_code="INVALID_IMAGE",
                detail=reason,
                retryable=False,
            )
        )
        stats["PLACEHOLDER_REJECTED"] += 1
        return record

    def record_duplicate_checksum(candidate: SourceCandidate, checksum: str) -> str | None:
        duplicate_checksum_of = first_by_checksum.get(checksum)
        if duplicate_checksum_of:
            stats["DUPLICATE_CHECKSUM"] += 1
            queues.append(
                queue_item(
                    drug_product_id=candidate.drug_product_id,
                    legacy_drug_id=candidate.legacy_drug_id,
                    source=candidate.source,
                    reason_code="DUPLICATE_REVIEW",
                    detail=f"same content checksum as {duplicate_checksum_of}; products are not merged",
                    retryable=False,
                )
            )
        else:
            first_by_checksum[checksum] = image_record_id(candidate)
        return duplicate_checksum_of

    def reuse_persisted_url_result(
        candidate: SourceCandidate, cached: ImageRecord, duplicate_url_of: str | None
    ) -> ImageRecord | None:
        """Reuse lightweight metadata and a persisted derivative for a duplicate URL."""

        checksum = cached.image_checksum_sha256
        if not checksum:
            return None
        stats["DOWNLOADED"] += 1
        if cached.validation_status == "REJECTED":
            return queue_placeholder(
                candidate,
                cached.validation_reason or "KNOWN_PLACEHOLDER_CHECKSUM",
                checksum=checksum,
                mime_type=cached.mime_type,
                file_size=cached.file_size,
                duplicate_url_of=duplicate_url_of,
            )
        if cached.validation_status == "INVALID":
            return queue_invalid(
                candidate,
                cached.validation_reason or "INVALID_IMAGE",
                checksum=checksum,
                mime_type=cached.mime_type,
                file_size=cached.file_size,
                duplicate_url_of=duplicate_url_of,
            )
        if cached.validation_status != "VALIDATED" or not valid_existing_record(cached, output_dir):
            stats["DOWNLOADED"] -= 1
            return None
        duplicate_checksum_of = record_duplicate_checksum(candidate, checksum)
        relative_path = Path("images") / candidate.drug_product_id / "primary.webp"
        copy_file_atomically(output_dir / str(cached.storage_relative_path), output_dir / relative_path)
        stats["VALIDATED"] += 1
        return make_record(
            candidate,
            retrieved_at=utc_now(),
            status="VALIDATED",
            reason=None,
            mime_type=cached.mime_type,
            checksum=checksum,
            normalized_checksum=cached.normalized_checksum_sha256,
            width=cached.width,
            height=cached.height,
            file_size=cached.file_size,
            storage_relative_path=relative_path.as_posix(),
            duplicate_url_of=duplicate_url_of,
            duplicate_checksum_of=duplicate_checksum_of,
        )

    for position, candidate in enumerate(candidates):
        if position and position % 25 == 0:
            checkpoint()
        record_id = image_record_id(candidate)
        prior = existing.get(record_id)
        if prior and valid_existing_record(prior, output_dir):
            records[record_id] = prior
            first_by_url.setdefault(candidate.original_image_url, record_id)
            if prior.image_checksum_sha256:
                first_by_checksum.setdefault(prior.image_checksum_sha256, record_id)
            remember_processed_url(prior)
            stats["RESUMED"] += 1
            stats["VALIDATED"] += 1
            continue
        if prior and prior.validation_status == "PLANNED" and not allow_source_download:
            records[record_id] = prior
            stats["RESUMED_PLANNED"] += 1
            continue
        if prior and not retry_failed and prior.validation_status != "VALIDATED":
            records[record_id] = prior
            stats["SKIPPED_FAILED"] += 1
            continue

        stats["ATTEMPTED"] += 1
        url_reason = validate_source_url(candidate.original_image_url)
        if url_reason:
            records[record_id] = queue_invalid(candidate, url_reason)
            continue
        duplicate_url_of = first_by_url.get(candidate.original_image_url)
        if duplicate_url_of:
            stats["DUPLICATE_URL"] += 1
        else:
            first_by_url[candidate.original_image_url] = record_id
        if candidate.original_image_url in known_placeholder_urls:
            records[record_id] = queue_placeholder(
                candidate, "KNOWN_PLACEHOLDER_URL", duplicate_url_of=duplicate_url_of
            )
            continue
        if not allow_source_download:
            records[record_id] = make_record(
                candidate,
                retrieved_at=utc_now(),
                status="PLANNED",
                reason="SOURCE_RIGHTS_REVIEW_REQUIRED",
                duplicate_url_of=duplicate_url_of,
            )
            stats["PLANNED"] += 1
            continue

        cached = processed_by_url.get(candidate.original_image_url)
        if cached:
            reused = reuse_persisted_url_result(candidate, cached, duplicate_url_of)
            if reused:
                records[record_id] = reused
                remember_processed_url(reused)
                continue

        content, content_type, download_reason = downloader.fetch(candidate.original_image_url)
        if download_reason or content is None:
            reason = download_reason or "HTTP_FAILURE"
            records[record_id] = make_record(
                candidate,
                retrieved_at=utc_now(),
                status="FAILED",
                reason=reason,
                mime_type=content_type,
                duplicate_url_of=duplicate_url_of,
            )
            queues.append(
                queue_item(
                    drug_product_id=candidate.drug_product_id,
                    legacy_drug_id=candidate.legacy_drug_id,
                    source=candidate.source,
                    reason_code="DOWNLOAD_FAILED",
                    detail=reason,
                    retryable=reason in {"TIMEOUT", "HTTP_FAILURE"} or reason.startswith("HTTP_5"),
                )
            )
            stats[reason] += 1
            continue
        stats["DOWNLOADED"] += 1
        checksum = hashlib.sha256(content).hexdigest()
        if checksum in known_placeholder_checksums:
            records[record_id] = queue_placeholder(
                candidate,
                "KNOWN_PLACEHOLDER_CHECKSUM",
                checksum=checksum,
                mime_type=content_type,
                file_size=len(content),
                duplicate_url_of=duplicate_url_of,
            )
            remember_processed_url(records[record_id])
            continue
        image, mime_type, validation_reason = validate_image_bytes(content, content_type)
        if validation_reason or image is None:
            records[record_id] = queue_invalid(
                candidate,
                validation_reason or "INVALID_IMAGE",
                checksum=checksum,
                mime_type=mime_type,
                file_size=len(content),
                duplicate_url_of=duplicate_url_of,
            )
            remember_processed_url(records[record_id])
            continue
        normalized = normalize_image(image)
        normalized_checksum = hashlib.sha256(normalized).hexdigest()
        duplicate_checksum_of = record_duplicate_checksum(candidate, checksum)
        relative_path = Path("images") / candidate.drug_product_id / "primary.webp"
        target_path = output_dir / relative_path
        temporary_path = unique_temporary_path(target_path)
        try:
            temporary_path.write_bytes(normalized)
            temporary_path.replace(target_path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        records[record_id] = make_record(
            candidate,
            retrieved_at=utc_now(),
            status="VALIDATED",
            reason=None,
            mime_type=mime_type,
            checksum=checksum,
            normalized_checksum=normalized_checksum,
            width=image.width,
            height=image.height,
            file_size=len(content),
            storage_relative_path=relative_path.as_posix(),
            duplicate_url_of=duplicate_url_of,
            duplicate_checksum_of=duplicate_checksum_of,
        )
        remember_processed_url(records[record_id])
        stats["VALIDATED"] += 1

    checkpoint()
    ordered_records = [records[key] for key in sorted(records)]
    return ordered_records, queues, stats


def write_source_queues(output_dir: Path, queues: list[QueueItem]) -> None:
    """Persist pre-download review queues separately from HTTP/image failures."""

    grouped: dict[str, list[QueueItem]] = defaultdict(list)
    for item in queues:
        grouped[item.reason_code].append(item)
    for reason_code, rows in grouped.items():
        write_jsonl(output_dir / "queues" / f"{reason_code.lower()}.jsonl", (asdict(item) for item in rows))


def main() -> int:
    """Run a B-02 dry-run or an explicitly approved collection."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--product-id", action="append")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--allow-source-download", action="store_true")
    parser.add_argument("--source-rights-status", choices=("APPROVED",))
    args = parser.parse_args()
    if args.dry_run and args.allow_source_download:
        parser.error("--dry-run cannot be combined with --allow-source-download")
    candidates, source_queues = load_source_candidates()
    if args.product_id:
        selected = set(args.product_id)
        candidates = [candidate for candidate in candidates if candidate.drug_product_id in selected]
    if args.limit is not None:
        candidates = candidates[: args.limit]
    with output_directory_lock(args.output_dir):
        write_source_queues(args.output_dir, source_queues)
        records, failures, stats = _collect(
            candidates,
            output_dir=args.output_dir,
            allow_source_download=args.allow_source_download,
            source_rights_status=args.source_rights_status,
            resume=args.resume,
            retry_failed=args.retry_failed,
        )
        summary = {
            "collection_version": COLLECTION_VERSION,
            "generated_at": utc_now(),
            "source_queue_counts": dict(Counter(item.reason_code for item in source_queues)),
            "stats": dict(stats),
            "record_count": len(records),
            "failure_count": len(failures),
            "dry_run": not args.allow_source_download,
        }
        write_text_atomically(
            args.output_dir / "summary.json",
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
