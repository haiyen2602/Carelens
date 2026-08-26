"""B-03 manifest import, primary-image and legacy-resolution coverage."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

os.environ["INTERNAL_AUTH_SECRET"] = "b03-local-test-secret"
os.environ["JWT_SECRET"] = "b03-local-test-jwt"

from backend.db.models import DrugIdMap, DrugImage, DrugProduct
from backend.services import drug_images
from backend.services.drug_images import (
    IMAGE_AVAILABLE,
    IMAGE_NO_IMAGE,
    FileSystemStorageBackend,
    drug_image_presentation,
    get_primary_drug_image,
    get_primary_drug_image_for_legacy_id,
    get_primary_drug_images,
    get_primary_drug_images_for_legacy_ids,
    import_manifest,
)


class CountingStorage(FileSystemStorageBackend):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.puts = 0

    def put_file(self, storage_key: str, source_path: Path) -> None:
        self.puts += 1
        super().put_file(storage_key, source_path)


def db_session() -> Session:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    DrugProduct.__table__.create(engine)
    DrugIdMap.__table__.create(engine)
    DrugImage.__table__.create(engine)
    return Session(engine)


def add_product(session: Session, product_id: str, legacy_id: str) -> None:
    session.add(
        DrugProduct(
            id=product_id,
            legacy_drug_id=legacy_id,
            display_name=product_id,
            status="ACTIVE",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()


def manifest_row(
    *, product_id: str = "product-1", record_id: str = "record-1", primary: bool = True
) -> dict[str, object]:
    return {
        "image_record_id": record_id,
        "drug_product_id": product_id,
        "legacy_drug_id": f"legacy-{product_id}",
        "storage_relative_path": f"images/{product_id}/primary.webp",
        "original_image_url": f"https://cdn.nhathuoclongchau.com.vn/{record_id}.jpg",
        "source_page_url": "https://nhathuoclongchau.com.vn/thuoc/example.html",
        "source_snapshot_id": f"snapshot-{record_id}",
        "source_product_id": "sku-1",
        "image_checksum_sha256": "a" * 64,
        "normalized_checksum_sha256": "",
        "mime_type": "image/jpeg",
        "width": 1000,
        "height": 1000,
        "file_size": 1024,
        "view_type": "front",
        "is_primary": primary,
        "validation_status": "VALIDATED",
        "collection_version": "drug-image-b02-v1",
        "retrieved_at": "2026-08-26T08:00:00+00:00",
    }


def write_manifest(
    tmp_path: Path, rows: list[dict[str, object]], *, payload: bytes = b"normalized-webp"
) -> tuple[Path, Path]:
    artifact_root = tmp_path / "artifact"
    for row in rows:
        image_path = artifact_root / str(row["storage_relative_path"])
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(payload)
        row["normalized_checksum_sha256"] = hashlib.sha256(payload).hexdigest()
    manifest_path = artifact_root / "manifest.jsonl"
    manifest_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return manifest_path, artifact_root


def test_manifest_import_creates_traceable_primary_and_deterministic_key(tmp_path: Path) -> None:
    session = db_session()
    add_product(session, "product-1", "legacy-product-1")
    manifest_path, artifact_root = write_manifest(tmp_path, [manifest_row()])
    storage = CountingStorage(tmp_path / "storage")

    counters = import_manifest(
        session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=False
    )
    session.commit()

    assert counters["WOULD_CREATE"] == 1
    row = session.get(DrugImage, "record-1")
    assert row is not None
    assert row.storage_key == "drug-images/drug-image-b02-v1/product-1/front/record-1.webp"
    assert storage.exists(row.storage_key)
    assert get_primary_drug_image(session, "product-1").id == "record-1"  # type: ignore[union-attr]


def test_filesystem_storage_copies_through_the_exclusive_temporary_descriptor(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "source.webp"
    source_path.write_bytes(b"verified-image")
    storage = FileSystemStorageBackend(tmp_path / "storage")
    synced_descriptors: list[int] = []
    monkeypatch.setattr(drug_images.os, "fsync", synced_descriptors.append)

    storage.put_file("drug-images/v1/product-1/front/record-1.webp", source_path)

    target = storage.path_for("drug-images/v1/product-1/front/record-1.webp")
    assert target.read_bytes() == b"verified-image"
    assert synced_descriptors
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_dry_run_makes_zero_database_or_storage_mutations(tmp_path: Path) -> None:
    session = db_session()
    add_product(session, "product-1", "legacy-product-1")
    manifest_path, artifact_root = write_manifest(tmp_path, [manifest_row()])
    storage = CountingStorage(tmp_path / "storage")

    counters = import_manifest(session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=True)
    session.rollback()

    assert counters["WOULD_CREATE"] == 1
    assert session.get(DrugImage, "record-1") is None
    assert storage.puts == 0


def test_idempotent_rerun_skips_duplicate_row_and_upload(tmp_path: Path) -> None:
    session = db_session()
    add_product(session, "product-1", "legacy-product-1")
    manifest_path, artifact_root = write_manifest(tmp_path, [manifest_row()])
    storage = CountingStorage(tmp_path / "storage")
    import_manifest(session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=False)
    session.commit()

    counters = import_manifest(
        session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=False
    )
    session.commit()

    assert counters["WOULD_SKIP"] == 1
    assert storage.puts == 1
    assert session.query(DrugImage).count() == 1


def test_missing_product_artifact_and_checksum_are_rejected(tmp_path: Path) -> None:
    session = db_session()
    row = manifest_row()
    manifest_path, artifact_root = write_manifest(tmp_path, [row])
    storage = CountingStorage(tmp_path / "storage")
    counters = import_manifest(session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=True)
    assert counters["PRODUCT_NOT_FOUND"] == 1

    add_product(session, "product-1", "legacy-product-1")
    (artifact_root / str(row["storage_relative_path"])).unlink()
    counters = import_manifest(session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=True)
    assert counters["IMAGE_FILE_MISSING"] == 1

    manifest_path, artifact_root = write_manifest(tmp_path, [row])
    row["normalized_checksum_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    counters = import_manifest(session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=True)
    assert counters["CHECKSUM_MISMATCH"] == 1


def test_duplicate_content_stays_owned_by_two_products(tmp_path: Path) -> None:
    session = db_session()
    add_product(session, "product-1", "legacy-product-1")
    add_product(session, "product-2", "legacy-product-2")
    rows = [manifest_row(), manifest_row(product_id="product-2", record_id="record-2")]
    manifest_path, artifact_root = write_manifest(tmp_path, rows)
    storage = CountingStorage(tmp_path / "storage")

    counters = import_manifest(
        session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=False
    )
    session.commit()

    assert counters["WOULD_CREATE"] == 2
    assert session.query(DrugImage).count() == 2
    assert {row.drug_product_id for row in session.query(DrugImage).all()} == {"product-1", "product-2"}
    assert storage.puts == 2


def test_only_one_validated_primary_per_product_collection_and_no_name_fallback(tmp_path: Path) -> None:
    session = db_session()
    add_product(session, "product-1", "legacy-product-1")
    rows = [manifest_row(record_id="record-1"), manifest_row(record_id="record-2")]
    manifest_path, artifact_root = write_manifest(tmp_path, rows)
    storage = CountingStorage(tmp_path / "storage")
    import_manifest(session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=False)
    session.commit()

    primary_rows = session.query(DrugImage).filter_by(is_primary=True, validation_status="VALIDATED").all()
    assert [row.id for row in primary_rows] == ["record-2"]
    assert get_primary_drug_image(session, "product-does-not-exist") is None


def test_failed_b02_row_is_excluded_and_legacy_lookup_uses_only_active_mapping(tmp_path: Path) -> None:
    session = db_session()
    add_product(session, "product-1", "legacy-product-1")
    row = manifest_row()
    row["validation_status"] = "FAILED"
    manifest_path, artifact_root = write_manifest(tmp_path, [row])
    storage = CountingStorage(tmp_path / "storage")
    counters = import_manifest(session, storage, manifest_path=manifest_path, artifact_root=artifact_root, dry_run=True)
    assert counters["INVALID_INPUT"] == 1

    valid_manifest, valid_root = write_manifest(tmp_path, [manifest_row()])
    import_manifest(session, storage, manifest_path=valid_manifest, artifact_root=valid_root, dry_run=False)
    session.add(
        DrugIdMap(
            id="map-1",
            legacy_drug_id="legacy-product-1",
            drug_product_id="product-1",
            mapping_status="ACTIVE",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()
    assert get_primary_drug_image_for_legacy_id(session, "legacy-product-1").id == "record-1"  # type: ignore[union-attr]
    assert get_primary_drug_image_for_legacy_id(session, "wrong-name") is None


def test_batch_lookup_keeps_exact_product_ownership_and_explicit_no_image(tmp_path: Path) -> None:
    session = db_session()
    add_product(session, "product-a", "legacy-a")
    add_product(session, "product-b", "legacy-b")
    manifest_path, artifact_root = write_manifest(tmp_path, [manifest_row(product_id="product-a", record_id="image-a")])
    import_manifest(
        session,
        CountingStorage(tmp_path / "storage"),
        manifest_path=manifest_path,
        artifact_root=artifact_root,
        dry_run=False,
    )
    session.add_all(
        (
            DrugIdMap(
                id="active-a",
                legacy_drug_id="legacy-a",
                drug_product_id="product-a",
                mapping_status="ACTIVE",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            DrugIdMap(
                id="retired-b",
                legacy_drug_id="legacy-b",
                drug_product_id="product-b",
                mapping_status="RETIRED",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        )
    )
    session.commit()

    by_product = get_primary_drug_images(session, ("product-a", "product-b"))
    by_legacy = get_primary_drug_images_for_legacy_ids(session, ("legacy-a", "legacy-b", "same-name"))

    assert set(by_product) == {"product-a"}
    assert by_product["product-a"].id == "image-a"
    assert set(by_legacy) == {"legacy-a"}
    assert by_legacy["legacy-a"].drug_product_id == "product-a"
    available = drug_image_presentation(by_product["product-a"], display_name="Thuốc A")
    missing = drug_image_presentation(by_product.get("product-b"), display_name="Thuốc B")
    assert (available.status, available.url) == (IMAGE_AVAILABLE, "/api/v1/drug-images/image-a")
    assert (missing.status, missing.url) == (IMAGE_NO_IMAGE, None)
