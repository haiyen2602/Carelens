"""Storage, import and lookup services for validated B-02 drug images.

This module intentionally has no FastAPI dependency.  It keeps the local
filesystem implementation replaceable and makes product-image persistence
testable without a production storage service.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.models import DrugIdMap, DrugImage, DrugProduct

logger = logging.getLogger(__name__)

VALIDATION_STATUS = "VALIDATED"
PRIMARY_VIEW = "front"
IMAGE_AVAILABLE = "AVAILABLE"
IMAGE_NO_IMAGE = "NO_IMAGE"
IMPORT_COUNTERS = (
    "TOTAL_MANIFEST",
    "VALIDATED_INPUT",
    "INVALID_INPUT",
    "PRODUCT_NOT_FOUND",
    "IMAGE_FILE_MISSING",
    "CHECKSUM_MISMATCH",
    "WOULD_CREATE",
    "WOULD_UPDATE",
    "WOULD_SKIP",
    "FAILED",
)


class DrugImageImportError(ValueError):
    """Raised when a manifest record cannot be imported safely."""


class StorageBackend(Protocol):
    """Minimal backend contract for deterministic catalog image objects."""

    def exists(self, storage_key: str) -> bool: ...

    def put_file(self, storage_key: str, source_path: Path) -> None: ...


class FileSystemStorageBackend:
    """Local-volume backend used by the existing project media conventions."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path_for(self, storage_key: str) -> Path:
        relative_path = Path(storage_key)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise DrugImageImportError("storage key must be a relative path")
        target = (self.root / relative_path).resolve()
        if self.root != target and self.root not in target.parents:
            raise DrugImageImportError("storage key escapes the configured storage root")
        return target

    def exists(self, storage_key: str) -> bool:
        return self.path_for(storage_key).is_file()

    def put_file(self, storage_key: str, source_path: Path) -> None:
        target = self.path_for(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        temporary_path = Path(temporary_name)
        try:
            # Keep the exclusively-created descriptor open while copying.  Reopening
            # the temporary path after mkstemp() would introduce a TOCTOU window.
            with source_path.open("rb") as source_handle, os.fdopen(descriptor, "wb") as temporary_handle:
                shutil.copyfileobj(source_handle, temporary_handle, length=1024 * 1024)
                temporary_handle.flush()
                os.fsync(temporary_handle.fileno())
            temporary_path.replace(target)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise


@dataclass(frozen=True)
class ManifestDrugImage:
    """Validated B-02 manifest fields allowed to cross into runtime storage."""

    image_record_id: str
    drug_product_id: str
    legacy_drug_id: str | None
    storage_relative_path: str
    source_url: str
    source_page_url: str | None
    source_snapshot_id: str
    source_product_id: str | None
    checksum_sha256: str
    normalized_checksum_sha256: str
    mime_type: str
    width: int
    height: int
    file_size: int
    view_type: str
    is_primary: bool
    collection_version: str
    source_retrieved_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ManifestDrugImage:
        if row.get("validation_status") != VALIDATION_STATUS:
            raise DrugImageImportError("only VALIDATED B-02 records may be imported")
        required_text = (
            "image_record_id",
            "drug_product_id",
            "storage_relative_path",
            "original_image_url",
            "source_snapshot_id",
            "image_checksum_sha256",
            "normalized_checksum_sha256",
            "mime_type",
            "view_type",
            "collection_version",
            "retrieved_at",
        )
        values: dict[str, str] = {}
        for field in required_text:
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                raise DrugImageImportError(f"manifest field {field!r} is required")
            values[field] = value.strip()
        dimensions = {field: row.get(field) for field in ("width", "height", "file_size")}
        if not all(isinstance(value, int) and value > 0 for value in dimensions.values()):
            raise DrugImageImportError("manifest image dimensions and file_size must be positive integers")
        try:
            retrieved_at = datetime.fromisoformat(values["retrieved_at"].replace("Z", "+00:00"))
        except ValueError as error:
            raise DrugImageImportError("manifest retrieved_at must be ISO-8601") from error
        if retrieved_at.tzinfo is None:
            raise DrugImageImportError("manifest retrieved_at must include timezone")
        is_primary = row.get("is_primary")
        if not isinstance(is_primary, bool):
            raise DrugImageImportError("manifest is_primary must be boolean")
        return cls(
            image_record_id=values["image_record_id"],
            drug_product_id=values["drug_product_id"],
            legacy_drug_id=_optional_text(row.get("legacy_drug_id")),
            storage_relative_path=_safe_relative_path(values["storage_relative_path"]),
            source_url=values["original_image_url"],
            source_page_url=_optional_text(row.get("source_page_url")),
            source_snapshot_id=values["source_snapshot_id"],
            source_product_id=_optional_text(row.get("source_product_id")),
            checksum_sha256=values["image_checksum_sha256"],
            normalized_checksum_sha256=values["normalized_checksum_sha256"],
            mime_type=values["mime_type"],
            width=int(dimensions["width"]),
            height=int(dimensions["height"]),
            file_size=int(dimensions["file_size"]),
            view_type=values["view_type"],
            is_primary=is_primary,
            collection_version=values["collection_version"],
            source_retrieved_at=retrieved_at.astimezone(UTC),
        )

    @property
    def storage_key(self) -> str:
        return (
            f"drug-images/{self.collection_version}/{self.drug_product_id}/{self.view_type}/{self.image_record_id}.webp"
        )


@dataclass(frozen=True)
class DrugImageLookup:
    """Internal, non-public result for downstream prescription/reminder code."""

    id: str
    drug_product_id: str
    storage_key: str
    width: int
    height: int
    view_type: str
    collection_version: str


@dataclass(frozen=True)
class DrugImagePresentation:
    """Patient-safe metadata for a canonically resolved catalog image."""

    status: str
    url: str | None
    alt: str
    view_type: str | None


def import_manifest(
    session: Session,
    storage: StorageBackend,
    *,
    manifest_path: Path,
    artifact_root: Path,
    dry_run: bool,
) -> Counter[str]:
    """Validate, copy and upsert B-02 records without name-based ownership."""

    counters: Counter[str] = Counter({counter: 0 for counter in IMPORT_COUNTERS})
    artifact_root = artifact_root.resolve()
    known_product_ids = set(session.scalars(select(DrugProduct.id)).all())
    existing_records = {row.id: row for row in session.scalars(select(DrugImage)).all()}
    for row in _read_jsonl(manifest_path):
        counters["TOTAL_MANIFEST"] += 1
        try:
            record = ManifestDrugImage.from_row(row)
        except DrugImageImportError:
            counters["INVALID_INPUT"] += 1
            continue
        counters["VALIDATED_INPUT"] += 1
        source_path = _artifact_path(artifact_root, record.storage_relative_path)
        if not source_path.is_file():
            counters["IMAGE_FILE_MISSING"] += 1
            continue
        if _sha256_file(source_path) != record.normalized_checksum_sha256:
            counters["CHECKSUM_MISMATCH"] += 1
            continue
        if record.drug_product_id not in known_product_ids:
            counters["PRODUCT_NOT_FOUND"] += 1
            continue
        current = existing_records.get(record.image_record_id)
        action = _action_for_record(current, record)
        if action == "WOULD_SKIP" and not storage.exists(record.storage_key):
            action = "WOULD_UPDATE"
        if action == "FAILED":
            counters["FAILED"] += 1
            continue
        counters[action] += 1
        if dry_run or action == "WOULD_SKIP":
            continue
        if not storage.exists(record.storage_key):
            storage.put_file(record.storage_key, source_path)
        if current is None:
            _retire_existing_primary(session, record)
            current = _new_image(record)
            session.add(current)
            existing_records[current.id] = current
        else:
            _apply_mutable_provenance(current, record)
            if record.is_primary:
                _retire_existing_primary(session, record, excluding_id=current.id)
    return counters


def get_primary_drug_image(session: Session, drug_product_id: str) -> DrugImageLookup | None:
    """Return only a validated primary image for the exact canonical product."""

    return get_primary_drug_images(session, (drug_product_id,)).get(drug_product_id)


def get_primary_drug_images(session: Session, drug_product_ids: Iterable[str]) -> dict[str, DrugImageLookup]:
    """Batch-resolve validated primary images by exact canonical product ID.

    The newest collection version wins for a product, matching the existing
    single-product lookup.  There is no name or checksum fallback.
    """

    product_ids = tuple(dict.fromkeys(product_id for product_id in drug_product_ids if product_id))
    if not product_ids:
        return {}
    rows = session.scalars(
        select(DrugImage)
        .where(
            DrugImage.drug_product_id.in_(product_ids),
            DrugImage.is_primary.is_(True),
            DrugImage.validation_status == VALIDATION_STATUS,
        )
        .order_by(DrugImage.drug_product_id, DrugImage.collection_version.desc(), DrugImage.id)
    ).all()
    resolved: dict[str, DrugImageLookup] = {}
    blocked_products: set[str] = set()
    selected_versions: dict[str, str] = {}
    for row in rows:
        if row.drug_product_id in blocked_products:
            continue
        if row.drug_product_id not in resolved:
            resolved[row.drug_product_id] = _lookup(row)
            selected_versions[row.drug_product_id] = row.collection_version
            continue
        if selected_versions[row.drug_product_id] == row.collection_version:
            logger.error(
                "DRUG_IMAGE_PRIMARY_INTEGRITY product_id=%s collection_version=%s",
                row.drug_product_id,
                row.collection_version,
            )
            resolved.pop(row.drug_product_id)
            blocked_products.add(row.drug_product_id)
    return resolved


def get_primary_drug_image_for_legacy_id(session: Session, legacy_drug_id: str) -> DrugImageLookup | None:
    """Resolve only an ACTIVE legacy mapping; never substitute by drug name."""

    product_id = session.scalar(
        select(DrugIdMap.drug_product_id).where(
            DrugIdMap.legacy_drug_id == legacy_drug_id,
            DrugIdMap.mapping_status == "ACTIVE",
        )
    )
    return get_primary_drug_image(session, product_id) if product_id else None


def get_primary_drug_images_for_legacy_ids(
    session: Session, legacy_drug_ids: Iterable[str]
) -> dict[str, DrugImageLookup]:
    """Batch-resolve only ACTIVE legacy mappings without name-based fallback."""

    mappings = get_active_drug_product_ids_for_legacy_ids(session, legacy_drug_ids)
    by_product = get_primary_drug_images(session, mappings.values())
    return {legacy_id: by_product[product_id] for legacy_id, product_id in mappings.items() if product_id in by_product}


def get_active_drug_product_ids_for_legacy_ids(session: Session, legacy_drug_ids: Iterable[str]) -> dict[str, str]:
    """Batch-resolve canonical product IDs through ACTIVE legacy mappings only."""

    legacy_ids = tuple(dict.fromkeys(legacy_id for legacy_id in legacy_drug_ids if legacy_id))
    if not legacy_ids:
        return {}
    mappings = session.execute(
        select(DrugIdMap.legacy_drug_id, DrugIdMap.drug_product_id).where(
            DrugIdMap.legacy_drug_id.in_(legacy_ids),
            DrugIdMap.mapping_status == "ACTIVE",
        )
    ).all()
    return dict(mappings)


def drug_image_presentation(
    image: DrugImageLookup | None, *, display_name: str, endpoint_prefix: str = "/api/v1/drug-images"
) -> DrugImagePresentation:
    """Create additive presentation metadata without exposing provenance/storage."""

    if image is None:
        return DrugImagePresentation(
            status=IMAGE_NO_IMAGE,
            url=None,
            alt="Chưa có hình ảnh thuốc",
            view_type=None,
        )
    return DrugImagePresentation(
        status=IMAGE_AVAILABLE,
        url=f"{endpoint_prefix}/{image.id}",
        alt=f"Hình ảnh bao bì {display_name}" if display_name else "Hình ảnh bao bì thuốc",
        view_type=image.view_type,
    )


def _action_for_record(current: DrugImage | None, record: ManifestDrugImage) -> str:
    if current is None:
        return "WOULD_CREATE"
    immutable = (
        current.drug_product_id,
        current.source_snapshot_id,
        current.source_url,
        current.checksum_sha256,
        current.normalized_checksum_sha256,
        current.view_type,
        current.collection_version,
        current.storage_key,
    )
    expected = (
        record.drug_product_id,
        record.source_snapshot_id,
        record.source_url,
        record.checksum_sha256,
        record.normalized_checksum_sha256,
        record.view_type,
        record.collection_version,
        record.storage_key,
    )
    if immutable != expected:
        return "FAILED"
    mutable = (
        current.source_page_url,
        current.source_product_id,
        current.legacy_drug_id,
        _utc(current.source_retrieved_at),
    )
    expected_mutable = (
        record.source_page_url,
        record.source_product_id,
        record.legacy_drug_id,
        record.source_retrieved_at,
    )
    return "WOULD_UPDATE" if mutable != expected_mutable or current.is_primary != record.is_primary else "WOULD_SKIP"


def _retire_existing_primary(session: Session, record: ManifestDrugImage, excluding_id: str | None = None) -> None:
    if not record.is_primary:
        return
    statement = (
        update(DrugImage)
        .where(
            DrugImage.drug_product_id == record.drug_product_id,
            DrugImage.collection_version == record.collection_version,
            DrugImage.is_primary.is_(True),
            DrugImage.validation_status == VALIDATION_STATUS,
        )
        .values(is_primary=False, updated_at=datetime.now(UTC))
    )
    if excluding_id:
        statement = statement.where(DrugImage.id != excluding_id)
    session.execute(statement)


def _new_image(record: ManifestDrugImage) -> DrugImage:
    return DrugImage(
        id=record.image_record_id,
        drug_product_id=record.drug_product_id,
        legacy_drug_id=record.legacy_drug_id,
        storage_key=record.storage_key,
        source_url=record.source_url,
        source_page_url=record.source_page_url,
        source_snapshot_id=record.source_snapshot_id,
        source_product_id=record.source_product_id,
        checksum_sha256=record.checksum_sha256,
        normalized_checksum_sha256=record.normalized_checksum_sha256,
        mime_type=record.mime_type,
        width=record.width,
        height=record.height,
        file_size=record.file_size,
        view_type=record.view_type,
        is_primary=record.is_primary,
        validation_status=VALIDATION_STATUS,
        collection_version=record.collection_version,
        source_retrieved_at=record.source_retrieved_at,
    )


def _apply_mutable_provenance(current: DrugImage, record: ManifestDrugImage) -> None:
    current.source_page_url = record.source_page_url
    current.source_product_id = record.source_product_id
    current.legacy_drug_id = record.legacy_drug_id
    current.source_retrieved_at = record.source_retrieved_at
    current.is_primary = record.is_primary
    current.updated_at = datetime.now(UTC)


def _lookup(row: DrugImage) -> DrugImageLookup:
    return DrugImageLookup(
        id=row.id,
        drug_product_id=row.drug_product_id,
        storage_key=row.storage_key,
        width=row.width,
        height=row.height,
        view_type=row.view_type,
        collection_version=row.collection_version,
    )


def _read_jsonl(path: Path) -> Iterator[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise DrugImageImportError(f"invalid JSONL at {path}:{line_number}") from error
            if not isinstance(row, dict):
                raise DrugImageImportError(f"manifest row at {path}:{line_number} must be an object")
            yield row


def _artifact_path(artifact_root: Path, storage_relative_path: str) -> Path:
    path = (artifact_root / storage_relative_path).resolve()
    if artifact_root != path and artifact_root not in path.parents:
        raise DrugImageImportError("manifest storage path escapes artifact root")
    return path


def _safe_relative_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise DrugImageImportError("manifest storage path must be relative")
    return path.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
