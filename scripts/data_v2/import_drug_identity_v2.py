"""Import Final Canonical V2 drug identity references into local PostgreSQL.

This DB-4B utility imports identity/reference data only. It deliberately does
not change the Drug Knowledge runtime facade, RAG artifacts, or operational
prescription and dose tables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_DIR = ROOT / "data pharmacy" / "v2" / "final_canonical"
IDENTITY_ARTIFACTS = (
    "drug_product.jsonl",
    "drug_id_map.jsonl",
    "ingredient.jsonl",
    "drug_product_ingredient.jsonl",
)
IMPORT_NAMESPACE = uuid.UUID("54e2b3d0-f5aa-5b2a-96cf-69d7d449675b")


@dataclass(frozen=True)
class SkippedLink:
    """A source relationship not representable in the DB-4A junction table."""

    reason: str
    drug_product_id: str
    ingredient_id: str | None
    legacy_drug_id: str | None


@dataclass(frozen=True)
class ImportPlan:
    """Validated source rows and reconciliation facts for one import run."""

    manifest_version: str
    artifact_hashes_before: dict[str, str]
    source_counts: dict[str, int]
    drug_products: list[dict[str, object]]
    drug_id_maps: list[dict[str, object]]
    ingredients: list[dict[str, object]]
    product_ingredients: list[dict[str, object]]
    skipped_links: list[SkippedLink]
    duplicate_valid_pairs: list[SkippedLink]


def sha256_file(path: Path) -> str:
    """Return the uppercase SHA-256 hash of a source artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def canonical_jsonl_sha256_file(path: Path) -> str:
    """Hash JSONL in its LF canonical form across Windows and Unix checkouts."""

    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest().upper()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read a UTF-8 JSONL artifact and reject malformed or non-object rows."""

    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{line_number} is not valid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path.name}:{line_number} must be a JSON object")
            rows.append(row)
    return rows


def require_text(row: Mapping[str, object], field: str, artifact_name: str) -> str:
    """Return a required non-blank text field with an actionable error."""

    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{artifact_name}: required text field {field!r} is missing")
    return value.strip()


def deterministic_id(kind: str, *parts: str) -> str:
    """Create a stable UUID string for artifacts that do not carry a row ID."""

    return str(uuid.uuid5(IMPORT_NAMESPACE, ":".join((kind, *parts))))


def assert_unique(rows: Iterable[Mapping[str, object]], field: str, artifact_name: str) -> None:
    """Reject duplicate required source IDs instead of silently choosing one."""

    values = [require_text(row, field, artifact_name) for row in rows]
    duplicate_values = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicate_values:
        preview = ", ".join(duplicate_values[:5])
        raise ValueError(f"{artifact_name}: duplicate {field} values: {preview}")


def load_import_plan(artifact_dir: Path) -> ImportPlan:
    """Validate Final Canonical identity artifacts and build DB-4A row payloads."""

    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_version = require_text(manifest, "version", "manifest.json")

    paths = {name: artifact_dir / name for name in IDENTITY_ARTIFACTS}
    missing_paths = [str(path) for path in paths.values() if not path.is_file()]
    if missing_paths:
        raise ValueError(f"Missing identity artifacts: {', '.join(missing_paths)}")

    artifact_hashes_before = {"manifest.json": sha256_file(manifest_path)}
    artifact_hashes_before.update({name: canonical_jsonl_sha256_file(path) for name, path in paths.items()})
    expected_hashes = manifest.get("artifact_hashes")
    if not isinstance(expected_hashes, dict):
        raise ValueError("manifest.json must declare artifact_hashes")
    for artifact_name in IDENTITY_ARTIFACTS:
        expected_hash = expected_hashes.get(artifact_name)
        actual_hash = artifact_hashes_before[artifact_name]
        if expected_hash != actual_hash:
            raise ValueError(
                f"manifest.json hash mismatch for {artifact_name}: "
                f"expected {expected_hash!r}, found {actual_hash!r}"
            )

    products_source = read_jsonl(paths["drug_product.jsonl"])
    mappings_source = read_jsonl(paths["drug_id_map.jsonl"])
    ingredients_source = read_jsonl(paths["ingredient.jsonl"])
    links_source = read_jsonl(paths["drug_product_ingredient.jsonl"])

    assert_unique(products_source, "id", "drug_product.jsonl")
    assert_unique(ingredients_source, "id", "ingredient.jsonl")
    assert_unique(mappings_source, "legacy_drug_id", "drug_id_map.jsonl")

    active_canonical = manifest.get("active_canonical")
    if active_canonical != len(products_source):
        raise ValueError(
            "manifest.json active_canonical must equal the number of canonical drug products "
            f"({active_canonical!r} != {len(products_source)})"
        )

    now = datetime.now(UTC)
    product_ids = {require_text(row, "id", "drug_product.jsonl") for row in products_source}
    ingredient_ids = {require_text(row, "id", "ingredient.jsonl") for row in ingredients_source}

    drug_products = [
        {
            "id": require_text(row, "id", "drug_product.jsonl"),
            "legacy_drug_id": require_text(row, "legacy_drug_id", "drug_product.jsonl"),
            "display_name": require_text(row, "display_name", "drug_product.jsonl"),
            "dosage_form": row.get("dosage_form"),
            "route": row.get("route"),
            "strength_text": None,
            "category_id": row.get("category"),
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
        }
        for row in products_source
    ]
    ingredients = [
        {
            "id": require_text(row, "id", "ingredient.jsonl"),
            "name": require_text(row, "canonical_name", "ingredient.jsonl"),
            "created_at": now,
            "updated_at": now,
        }
        for row in ingredients_source
    ]

    drug_id_maps: list[dict[str, object]] = []
    for row in mappings_source:
        legacy_drug_id = require_text(row, "legacy_drug_id", "drug_id_map.jsonl")
        drug_product_id = require_text(row, "drug_product_id", "drug_id_map.jsonl")
        if drug_product_id not in product_ids:
            raise ValueError(
                f"drug_id_map.jsonl: {legacy_drug_id} references missing product {drug_product_id}"
            )
        drug_id_maps.append(
            {
                "id": deterministic_id("drug-id-map", legacy_drug_id, drug_product_id),
                "legacy_drug_id": legacy_drug_id,
                "drug_product_id": drug_product_id,
                "mapping_status": "ACTIVE",
                "source_manifest_version": manifest_version,
                "created_at": now,
                "updated_at": now,
            }
        )

    product_ingredients: list[dict[str, object]] = []
    skipped_links: list[SkippedLink] = []
    duplicate_valid_pairs: list[SkippedLink] = []
    seen_pairs: set[tuple[str, str]] = set()
    for row in links_source:
        product_id = require_text(row, "drug_product_id", "drug_product_ingredient.jsonl")
        ingredient_id = row.get("ingredient_id")
        legacy_drug_id = row.get("legacy_drug_id")
        if not isinstance(ingredient_id, str) or not ingredient_id.strip():
            skipped_links.append(
                SkippedLink("MISSING_CANONICAL_INGREDIENT", product_id, None, _optional_text(legacy_drug_id))
            )
            continue
        ingredient_id = ingredient_id.strip()
        if product_id not in product_ids:
            raise ValueError(f"drug_product_ingredient.jsonl: missing product {product_id}")
        if ingredient_id not in ingredient_ids:
            raise ValueError(f"drug_product_ingredient.jsonl: missing ingredient {ingredient_id}")
        pair = (product_id, ingredient_id)
        if pair in seen_pairs:
            duplicate_valid_pairs.append(
                SkippedLink("DUPLICATE_PRODUCT_INGREDIENT_PAIR", product_id, ingredient_id, _optional_text(legacy_drug_id))
            )
            continue
        seen_pairs.add(pair)
        product_ingredients.append(
            {
                "id": deterministic_id("drug-product-ingredient", product_id, ingredient_id),
                "drug_product_id": product_id,
                "ingredient_id": ingredient_id,
                "created_at": now,
            }
        )

    return ImportPlan(
        manifest_version=manifest_version,
        artifact_hashes_before=artifact_hashes_before,
        source_counts={
            "drug_product": len(products_source),
            "drug_id_map": len(mappings_source),
            "ingredient": len(ingredients_source),
            "drug_product_ingredient": len(links_source),
        },
        drug_products=drug_products,
        drug_id_maps=drug_id_maps,
        ingredients=ingredients,
        product_ingredients=product_ingredients,
        skipped_links=skipped_links,
        duplicate_valid_pairs=duplicate_valid_pairs,
    )


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def assert_local_postgres_url(database_url: str) -> None:
    """Refuse non-local targets so DB-4B cannot touch shared environments."""

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError("DATABASE_URL must use the PostgreSQL scheme")
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("DB-4B only permits a local PostgreSQL target")


def reflect_identity_tables(engine: sa.Engine) -> dict[str, sa.Table]:
    """Load the DB-4A identity tables without changing the ORM or migration."""

    metadata = sa.MetaData()
    return {
        name: sa.Table(name, metadata, autoload_with=engine)
        for name in ("drug_product", "drug_id_map", "ingredient", "drug_product_ingredient")
    }


def table_counts(connection: sa.Connection, tables: Mapping[str, sa.Table]) -> dict[str, int]:
    """Return exact table counts for reconciliation before and after import."""

    return {name: int(connection.scalar(sa.select(sa.func.count()).select_from(table)) or 0) for name, table in tables.items()}


def upsert_identity_rows(engine: sa.Engine, plan: ImportPlan) -> dict[str, dict[str, int]]:
    """Atomically import all DB-4B reference rows and return count deltas."""

    tables = reflect_identity_tables(engine)
    with engine.begin() as connection:
        before = table_counts(connection, tables)
        _upsert_by_primary_key(connection, tables["drug_product"], plan.drug_products, ("id",))
        _upsert_by_primary_key(connection, tables["ingredient"], plan.ingredients, ("id",))
        _upsert_by_primary_key(connection, tables["drug_id_map"], plan.drug_id_maps, ("id",))
        _insert_pairs(connection, tables["drug_product_ingredient"], plan.product_ingredients)
        after = table_counts(connection, tables)
    return {
        "before": before,
        "after": after,
        "created": {name: after[name] - before[name] for name in after},
    }


def _upsert_by_primary_key(
    connection: sa.Connection, table: sa.Table, rows: list[dict[str, object]], key_columns: tuple[str, ...]
) -> None:
    """Upsert identity rows by stable source/deterministic IDs in bounded batches."""

    for batch in _batches(rows, 500):
        statement = pg_insert(table).values(batch)
        mutable_columns = {
            column.name: statement.excluded[column.name]
            for column in table.columns
            if column.name not in key_columns and column.name != "created_at"
        }
        connection.execute(statement.on_conflict_do_update(index_elements=list(key_columns), set_=mutable_columns))


def _insert_pairs(connection: sa.Connection, table: sa.Table, rows: list[dict[str, object]]) -> None:
    """Insert unique product/ingredient pairs without duplicating prior imports."""

    for batch in _batches(rows, 500):
        statement = pg_insert(table).values(batch)
        connection.execute(
            statement.on_conflict_do_nothing(constraint="uq_drug_product_ingredient_pair")
        )


def _batches(rows: list[dict[str, object]], size: int) -> Iterable[list[dict[str, object]]]:
    """Yield bounded insert batches to keep SQL statements manageable."""

    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def artifact_hashes_after(artifact_dir: Path) -> dict[str, str]:
    """Re-hash all imported source files after work to prove they were untouched."""

    files = {"manifest.json": artifact_dir / "manifest.json"}
    files.update({name: artifact_dir / name for name in IDENTITY_ARTIFACTS})
    return {
        name: sha256_file(path) if name == "manifest.json" else canonical_jsonl_sha256_file(path)
        for name, path in files.items()
    }


def build_summary(plan: ImportPlan, result: dict[str, dict[str, int]] | None, artifact_dir: Path) -> dict[str, object]:
    """Create machine-readable reconciliation data for validation and report writing."""

    hashes_after = artifact_hashes_after(artifact_dir)
    return {
        "manifest_version": plan.manifest_version,
        "source_counts": plan.source_counts,
        "importable_counts": {
            "drug_product": len(plan.drug_products),
            "drug_id_map": len(plan.drug_id_maps),
            "ingredient": len(plan.ingredients),
            "drug_product_ingredient": len(plan.product_ingredients),
        },
        "skipped_link_count": len(plan.skipped_links),
        "duplicate_valid_pair_count": len(plan.duplicate_valid_pairs),
        "skipped_links": [asdict(item) for item in plan.skipped_links],
        "duplicate_valid_pairs": [asdict(item) for item in plan.duplicate_valid_pairs],
        "artifact_hashes_before": plan.artifact_hashes_before,
        "artifact_hashes_after": hashes_after,
        "artifacts_unchanged": plan.artifact_hashes_before == hashes_after,
        "database": result,
    }


def build_console_summary(summary: dict[str, object]) -> dict[str, object]:
    """Keep terminal output reviewable while retaining exceptions in the JSON report."""

    return {
        key: value
        for key, value in summary.items()
        if key not in {"skipped_links", "duplicate_valid_pairs"}
    }


def parse_args() -> argparse.Namespace:
    """Parse the DB-4B CLI without providing a production-default database URL."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true", help="Validate source artifacts without connecting to PostgreSQL")
    parser.add_argument("--summary-json", type=Path, help="Optional path for a generated validation summary")
    return parser.parse_args()


def main() -> int:
    """Run a safe DB-4B import or source-only dry run."""

    args = parse_args()
    try:
        artifact_dir = args.artifact_dir.resolve()
        plan = load_import_plan(artifact_dir)
        result: dict[str, dict[str, int]] | None = None
        if not args.dry_run:
            if not args.database_url:
                raise ValueError("DATABASE_URL or --database-url is required unless --dry-run is used")
            assert_local_postgres_url(args.database_url)
            engine = sa.create_engine(args.database_url, future=True, pool_pre_ping=True)
            try:
                result = upsert_identity_rows(engine, plan)
            finally:
                engine.dispose()
        summary = build_summary(plan, result, artifact_dir)
    except (OSError, ValueError, SQLAlchemyError) as exc:
        print(f"DB-4B import failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(build_console_summary(summary), ensure_ascii=False, indent=2, default=str))
    if args.summary_json:
        args.summary_json.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
