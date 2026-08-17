#!/usr/bin/env python3
"""Backfill legacy ``prescription.items`` into additive V2 prescription tables.

DB-4C intentionally writes only ``prescription_item``, ``medication_plan``,
and valid ``schedule_rule`` rows. It never creates dose occurrences, changes a
legacy prescription, or switches runtime reads/writes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

MIGRATION_SOURCE = "legacy_prescription"
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
LOCAL_TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE)
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
ACTIVE_LEGACY_STATUSES = frozenset({"active", "approved"})
STATUS_MAP = {
    "draft": "DRAFT",
    "approved": "ACTIVE",
    "active": "ACTIVE",
    "completed": "COMPLETED",
    "stopped": "STOPPED",
    "rejected": "REJECTED",
}
TARGET_TABLES = ("prescription_item", "medication_plan", "schedule_rule")


@dataclass(frozen=True)
class SourceIssue:
    """One source item requiring review instead of an unsafe inferred value."""

    prescription_id: str
    item_index: int | None
    reason: str
    detail: str | None = None
    legacy_drug_id: str | None = None


@dataclass
class BackfillPlan:
    """Validated source projection and review exceptions before any write."""

    prescription_items: list[dict[str, Any]] = field(default_factory=list)
    medication_plans: list[dict[str, Any]] = field(default_factory=list)
    schedule_rules: list[dict[str, Any]] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    status_counts: Counter[str] = field(default_factory=Counter)
    unmapped_drug_ids: list[SourceIssue] = field(default_factory=list)
    invalid_schedules: list[SourceIssue] = field(default_factory=list)
    invalid_dates: list[SourceIssue] = field(default_factory=list)
    malformed_items: list[SourceIssue] = field(default_factory=list)
    active_prescriptions_without_items: list[str] = field(default_factory=list)


def deterministic_id(namespace: str, *parts: object) -> str:
    """Generate a stable UUIDv5 target ID from a legacy source location."""

    value = ":".join(str(part) for part in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vmec-db4c:{namespace}:{value}"))


def assert_local_postgres_url(database_url: str) -> None:
    """Reject Railway and other shared targets before opening a connection."""

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise ValueError("database URL must use PostgreSQL")
    hostname = (parsed.hostname or "").lower()
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("DB-4C accepts local PostgreSQL URLs only")


def normalize_text(value: object) -> str | None:
    """Retain a raw string when present; do not manufacture clinical text."""

    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def parse_schedule_times(value: object) -> tuple[list[str] | None, str | None]:
    """Accept only a non-empty, unique list of strict ``HH:MM`` reminder times."""

    if not isinstance(value, list) or not value:
        return None, "MISSING_OR_NON_LIST_GIO_NHAC"
    if not all(isinstance(item, str) and TIME_RE.fullmatch(item) for item in value):
        return None, "INVALID_GIO_NHAC_TIME"
    if len(set(value)) != len(value):
        return None, "DUPLICATE_GIO_NHAC_TIME"
    return sorted(value), None


def parse_date_range(
    prescription: dict[str, Any], item: dict[str, Any]
) -> tuple[date | None, date | None, str | None]:
    """Map legacy inclusive-day duration to V2's exclusive end-date boundary."""

    raw_start = item.get("start_date") if item.get("start_date") not in (None, "") else prescription.get("start_date")
    raw_duration = item.get("duration_days") if item.get("duration_days") not in (None, "") else prescription.get("duration_days")
    try:
        start = date.fromisoformat(str(raw_start))
    except (TypeError, ValueError):
        return None, None, "INVALID_START_DATE"
    try:
        if isinstance(raw_duration, bool):
            raise ValueError
        duration = int(raw_duration)
        if duration <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return start, None, "INVALID_DURATION_DAYS"
    return start, start + timedelta(days=duration), None


def local_midnight_as_utc(value: date | None) -> datetime | None:
    """Represent a legacy Vietnam-local date boundary as a timezone-aware instant."""

    if value is None:
        return None
    return datetime.combine(value, time.min, tzinfo=LOCAL_TIMEZONE).astimezone(UTC)


def _active_mapping_lookup(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Build a fail-closed active legacy-ID lookup from imported DB-4B data."""

    mapping: dict[str, str] = {}
    for row in rows:
        legacy_id = str(row["legacy_drug_id"])
        product_id = str(row["drug_product_id"])
        prior = mapping.get(legacy_id)
        if prior is not None and prior != product_id:
            raise ValueError(f"multiple active drug_id_map products for {legacy_id!r}")
        mapping[legacy_id] = product_id
    return mapping


def _normalized_status(value: object) -> str:
    return str(value or "").strip().lower()


def _plan_status(legacy_status: str, *, mapped: bool, schedule_valid: bool, dates_valid: bool) -> str:
    """Never leave an uncertain migration result actionable."""

    mapped_status = STATUS_MAP.get(legacy_status, "REVIEW_REQUIRED")
    if not mapped or not schedule_valid or not dates_valid:
        return "REVIEW_REQUIRED"
    return mapped_status


def build_backfill_plan(
    prescriptions: Iterable[dict[str, Any]], active_mapping: dict[str, str]
) -> BackfillPlan:
    """Validate and project every legacy item without writing to PostgreSQL."""

    plan = BackfillPlan()
    for prescription in prescriptions:
        prescription_id = str(prescription["id"])
        legacy_status = _normalized_status(prescription.get("status"))
        plan.status_counts[legacy_status or "<missing>"] += 1
        raw_items = prescription.get("items")
        if not isinstance(raw_items, list):
            plan.malformed_items.append(SourceIssue(prescription_id, None, "ITEMS_NOT_A_LIST"))
            if legacy_status in ACTIVE_LEGACY_STATUSES:
                plan.active_prescriptions_without_items.append(prescription_id)
            continue

        plan.source_counts["legacy_items"] = plan.source_counts.get("legacy_items", 0) + len(raw_items)
        imported_for_prescription = 0
        for item_index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                plan.malformed_items.append(
                    SourceIssue(prescription_id, item_index, "ITEM_NOT_AN_OBJECT")
                )
                continue

            legacy_drug_id = normalize_text(item.get("drug_id"))
            drug_product_id = active_mapping.get(legacy_drug_id) if legacy_drug_id else None
            if drug_product_id is None:
                plan.unmapped_drug_ids.append(
                    SourceIssue(
                        prescription_id,
                        item_index,
                        "MISSING_LEGACY_DRUG_ID" if legacy_drug_id is None else "NO_ACTIVE_DRUG_ID_MAP",
                        legacy_drug_id=legacy_drug_id,
                    )
                )

            times_of_day, schedule_error = parse_schedule_times(item.get("gio_nhac"))
            if schedule_error:
                plan.invalid_schedules.append(
                    SourceIssue(prescription_id, item_index, schedule_error, legacy_drug_id=legacy_drug_id)
                )

            start_date, end_date, date_error = parse_date_range(prescription, item)
            if date_error:
                plan.invalid_dates.append(
                    SourceIssue(prescription_id, item_index, date_error, legacy_drug_id=legacy_drug_id)
                )

            prescription_item_id = deterministic_id("prescription-item", prescription_id, item_index)
            medication_plan_id = deterministic_id("medication-plan", prescription_item_id)
            schedule_rule_id = deterministic_id("schedule-rule", medication_plan_id)
            item_status = STATUS_MAP.get(legacy_status, "REVIEW_REQUIRED")
            medication_status = _plan_status(
                legacy_status,
                mapped=drug_product_id is not None,
                schedule_valid=times_of_day is not None,
                dates_valid=date_error is None,
            )

            plan.prescription_items.append(
                {
                    "id": prescription_item_id,
                    "prescription_id": prescription_id,
                    "patient_id": str(prescription["patient_id"]),
                    "drug_product_id": drug_product_id,
                    "legacy_drug_id": legacy_drug_id,
                    "drug_display_name": normalize_text(item.get("ten_thuoc")),
                    "dose_text": normalize_text(item.get("lieu_dung")),
                    "dose_value": None,
                    "dose_unit": None,
                    "route": normalize_text(item.get("duong_dung")),
                    "frequency_text": normalize_text(item.get("thoi_diem_dung")),
                    "instructions": normalize_text(item.get("instructions")) or normalize_text(prescription.get("note")),
                    "start_date": start_date,
                    "end_date": end_date,
                    "status": item_status,
                    "migration_source": MIGRATION_SOURCE,
                    "migration_source_id": prescription_id,
                    "migration_item_index": item_index,
                }
            )
            plan.medication_plans.append(
                {
                    "id": medication_plan_id,
                    "patient_id": str(prescription["patient_id"]),
                    "prescription_item_id": prescription_item_id,
                    "drug_product_id": drug_product_id,
                    "legacy_drug_id": legacy_drug_id,
                    "status": medication_status,
                    "timezone": DEFAULT_TIMEZONE,
                    "start_at": local_midnight_as_utc(start_date),
                    "end_at": local_midnight_as_utc(end_date),
                    "instructions": normalize_text(item.get("instructions")) or normalize_text(prescription.get("note")),
                }
            )
            if times_of_day is not None:
                plan.schedule_rules.append(
                    {
                        "id": schedule_rule_id,
                        "medication_plan_id": medication_plan_id,
                        "rule_type": "DAILY",
                        "frequency": len(times_of_day),
                        "interval_value": 1,
                        "interval_unit": "DAY",
                        "times_of_day": times_of_day,
                        "days_of_week": None,
                        "day_of_month": None,
                        "start_at": local_midnight_as_utc(start_date),
                        "end_at": local_midnight_as_utc(end_date),
                        "timezone": DEFAULT_TIMEZONE,
                        "status": "ACTIVE" if medication_status == "ACTIVE" else "DRAFT",
                    }
                )
            imported_for_prescription += 1

        if legacy_status in ACTIVE_LEGACY_STATUSES and imported_for_prescription == 0:
            plan.active_prescriptions_without_items.append(prescription_id)

    plan.source_counts.setdefault("legacy_items", 0)
    return plan


def _reflect_tables(engine: sa.Engine) -> dict[str, sa.Table]:
    metadata = sa.MetaData()
    return {
        name: sa.Table(name, metadata, autoload_with=engine)
        for name in ("prescription", "drug_id_map", *TARGET_TABLES)
    }


def load_plan_from_database(engine: sa.Engine) -> BackfillPlan:
    """Read every legacy prescription and active DB-4B mapping before writing."""

    tables = _reflect_tables(engine)
    with engine.connect() as connection:
        prescriptions = [dict(row) for row in connection.execute(sa.select(tables["prescription"]).order_by(tables["prescription"].c.id)).mappings()]
        mapping_rows = [
            dict(row)
            for row in connection.execute(
                sa.select(tables["drug_id_map"].c.legacy_drug_id, tables["drug_id_map"].c.drug_product_id).where(
                    tables["drug_id_map"].c.mapping_status == "ACTIVE"
                )
            ).mappings()
        ]
    plan = build_backfill_plan(prescriptions, _active_mapping_lookup(mapping_rows))
    plan.source_counts["legacy_prescriptions"] = len(prescriptions)
    return plan


def _batches(rows: list[dict[str, Any]], size: int = 250) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _upsert(connection: sa.Connection, table: sa.Table, rows: list[dict[str, Any]], key_columns: tuple[str, ...]) -> None:
    """Upsert deterministic migration rows without modifying created timestamps."""

    now = datetime.now(UTC)
    for batch in _batches(rows):
        values = [{**row, "created_at": now, "updated_at": now} for row in batch]
        statement = pg_insert(table).values(values)
        mutable_columns = {
            column.name: getattr(statement.excluded, column.name)
            for column in table.columns
            if column.name not in {"id", "created_at", *key_columns}
        }
        connection.execute(statement.on_conflict_do_update(index_elements=list(key_columns), set_=mutable_columns))


def table_counts(connection: sa.Connection) -> dict[str, int]:
    tables = _reflect_tables(connection.engine)
    return {
        name: int(connection.execute(sa.select(sa.func.count()).select_from(tables[name])).scalar_one())
        for name in TARGET_TABLES
    }


def backfill(engine: sa.Engine, plan: BackfillPlan) -> dict[str, dict[str, int]]:
    """Write validated rows in per-prescription transactions for resumability."""

    tables = _reflect_tables(engine)
    with engine.connect() as connection:
        before = {
            name: int(connection.execute(sa.select(sa.func.count()).select_from(tables[name])).scalar_one())
            for name in TARGET_TABLES
        }

    items_by_prescription: dict[str, list[dict[str, Any]]] = {}
    plans_by_prescription: dict[str, list[dict[str, Any]]] = {}
    rules_by_prescription: dict[str, list[dict[str, Any]]] = {}
    item_to_prescription: dict[str, str] = {}
    plan_to_prescription: dict[str, str] = {}
    for row in plan.prescription_items:
        items_by_prescription.setdefault(str(row["prescription_id"]), []).append(row)
        item_to_prescription[str(row["id"])] = str(row["prescription_id"])
    for row in plan.medication_plans:
        source_id = item_to_prescription[str(row["prescription_item_id"])]
        plans_by_prescription.setdefault(source_id, []).append(row)
        plan_to_prescription[str(row["id"])] = source_id
    for row in plan.schedule_rules:
        source_id = plan_to_prescription[str(row["medication_plan_id"])]
        rules_by_prescription.setdefault(source_id, []).append(row)

    for prescription_id, items in items_by_prescription.items():
        with engine.begin() as connection:
            _upsert(
                connection,
                tables["prescription_item"],
                items,
                ("migration_source", "migration_source_id", "migration_item_index"),
            )
            _upsert(connection, tables["medication_plan"], plans_by_prescription[prescription_id], ("id",))
            _upsert(connection, tables["schedule_rule"], rules_by_prescription.get(prescription_id, []), ("id",))

    with engine.connect() as connection:
        after = {
            name: int(connection.execute(sa.select(sa.func.count()).select_from(tables[name])).scalar_one())
            for name in TARGET_TABLES
        }
    return {
        "before": before,
        "after": after,
        "created": {name: after[name] - before[name] for name in TARGET_TABLES},
    }


def validation_counts(engine: sa.Engine) -> dict[str, int]:
    """Return DB-4C integrity gate counts; every value should be zero."""

    tables = _reflect_tables(engine)
    item = tables["prescription_item"]
    medication_plan = tables["medication_plan"]
    schedule_rule = tables["schedule_rule"]
    prescription = tables["prescription"]
    metadata = sa.MetaData()
    drug_product = sa.Table("drug_product", metadata, autoload_with=engine)
    with engine.connect() as connection:
        return {
            "duplicate_migration_keys": int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(
                        sa.select(item.c.migration_source, item.c.migration_source_id, item.c.migration_item_index)
                        .where(item.c.migration_source == MIGRATION_SOURCE)
                        .group_by(item.c.migration_source, item.c.migration_source_id, item.c.migration_item_index)
                        .having(sa.func.count() > 1)
                        .subquery()
                    )
                ).scalar_one()
            ),
            "item_missing_legacy_prescription": int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(item.outerjoin(prescription, item.c.prescription_id == prescription.c.id)).where(prescription.c.id.is_(None))
                ).scalar_one()
            ),
            "plan_missing_prescription_item": int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(medication_plan.outerjoin(item, medication_plan.c.prescription_item_id == item.c.id)).where(item.c.id.is_(None))
                ).scalar_one()
            ),
            "rule_missing_medication_plan": int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(schedule_rule.outerjoin(medication_plan, schedule_rule.c.medication_plan_id == medication_plan.c.id)).where(medication_plan.c.id.is_(None))
                ).scalar_one()
            ),
            "item_missing_drug_product": int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(item.outerjoin(drug_product, item.c.drug_product_id == drug_product.c.id)).where(item.c.drug_product_id.is_not(None), drug_product.c.id.is_(None))
                ).scalar_one()
            ),
            "plan_missing_drug_product": int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(medication_plan.outerjoin(drug_product, medication_plan.c.drug_product_id == drug_product.c.id)).where(medication_plan.c.drug_product_id.is_not(None), drug_product.c.id.is_(None))
                ).scalar_one()
            ),
        }


def build_summary(plan: BackfillPlan, database: dict[str, dict[str, int]] | None, validation: dict[str, int] | None) -> dict[str, Any]:
    """Create a complete machine-readable reconciliation report."""

    return {
        "migration_source": MIGRATION_SOURCE,
        "source_counts": plan.source_counts,
        "status_counts": dict(sorted(plan.status_counts.items())),
        "backfillable_counts": {
            "prescription_item": len(plan.prescription_items),
            "medication_plan": len(plan.medication_plans),
            "schedule_rule": len(plan.schedule_rules),
        },
        "unmapped_drug_ids": [asdict(issue) for issue in plan.unmapped_drug_ids],
        "invalid_schedules": [asdict(issue) for issue in plan.invalid_schedules],
        "invalid_dates": [asdict(issue) for issue in plan.invalid_dates],
        "malformed_items": [asdict(issue) for issue in plan.malformed_items],
        "active_prescriptions_without_items": plan.active_prescriptions_without_items,
        "database": database,
        "validation": validation,
    }


def build_console_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Keep terminal output concise while retaining source exceptions in JSON."""

    return {
        key: value
        for key, value in summary.items()
        if key
        not in {
            "unmapped_drug_ids",
            "invalid_schedules",
            "invalid_dates",
            "malformed_items",
            "active_prescriptions_without_items",
        }
    } | {
        "unmapped_drug_id_count": len(summary["unmapped_drug_ids"]),
        "invalid_schedule_count": len(summary["invalid_schedules"]),
        "invalid_date_count": len(summary["invalid_dates"]),
        "malformed_item_count": len(summary["malformed_items"]),
        "active_prescriptions_without_item_count": len(summary["active_prescriptions_without_items"]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true", help="Validate source rows without writing")
    parser.add_argument("--summary-json", type=Path, help="Optional JSON validation output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not args.database_url:
            raise ValueError("DATABASE_URL or --database-url is required")
        assert_local_postgres_url(args.database_url)
        engine = sa.create_engine(args.database_url, future=True, pool_pre_ping=True)
        try:
            plan = load_plan_from_database(engine)
            database = None if args.dry_run else backfill(engine, plan)
            validation = None if args.dry_run else validation_counts(engine)
        finally:
            engine.dispose()
        summary = build_summary(plan, database, validation)
    except (OSError, ValueError, SQLAlchemyError) as exc:
        print(f"DB-4C backfill failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(build_console_summary(summary), ensure_ascii=False, indent=2, default=str))
    if args.summary_json:
        args.summary_json.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
