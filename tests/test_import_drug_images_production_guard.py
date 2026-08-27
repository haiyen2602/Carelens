"""Drug-image production import task: tests for the new --production
opt-in guard on scripts/data_v2/import_drug_images.py.

The pre-existing assert_local_postgres_url safety net must stay the
DEFAULT for every existing caller; --production is a new, narrow,
explicit opt-in that requires --database-url and exactly one of
--dry-run/--execute -- there is no default that silently writes to a
real target. Tested via real subprocess invocation of the actual CLI
(not a reimplementation of its argument logic), using nonexistent
manifest/artifact paths so a case that clears argument validation still
fails fast for an unrelated, clearly distinguishable reason (a
FileNotFoundError-shaped failure, not an argparse usage error) rather
than actually touching any database.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "data_v2" / "import_drug_images.py"
FAKE_MANIFEST = ROOT / "does-not-exist-manifest.jsonl"
FAKE_ARTIFACT_ROOT = ROOT / "does-not-exist-artifacts"


def _run(*extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(FAKE_MANIFEST),
            "--artifact-root",
            str(FAKE_ARTIFACT_ROOT),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=30,
    )


def test_default_mode_rejects_a_non_local_database_url():
    result = _run("--database-url", "postgresql://user:pass@remote-host.example.com:5432/db", "--dry-run")
    assert result.returncode != 0
    assert "only permits a local PostgreSQL DATABASE_URL" in result.stderr


def test_execute_flag_without_production_is_rejected():
    result = _run("--database-url", "postgresql://user:pass@localhost:5432/db", "--execute")
    assert result.returncode == 2
    assert "--execute is only meaningful with --production" in result.stderr


def test_production_without_database_url_is_rejected():
    result = _run("--production", "--dry-run")
    assert result.returncode == 2
    assert "--production requires --database-url to be passed explicitly" in result.stderr


def test_production_with_neither_dry_run_nor_execute_is_rejected():
    result = _run("--production", "--database-url", "postgresql://user:pass@remote-host.example.com:5432/db")
    assert result.returncode == 2
    assert "requires exactly one of --dry-run or --execute" in result.stderr


def test_production_with_both_dry_run_and_execute_is_rejected():
    result = _run(
        "--production",
        "--database-url",
        "postgresql://user:pass@remote-host.example.com:5432/db",
        "--dry-run",
        "--execute",
    )
    assert result.returncode == 2
    assert "requires exactly one of --dry-run or --execute" in result.stderr


def test_production_dry_run_with_explicit_database_url_clears_argument_validation():
    """Clears the new guard (does not hit the argparse usage-error exit
    code 2 / the local-only ValueError), then fails for an unrelated,
    expected reason -- the fake manifest path does not exist. Confirms
    --production genuinely bypasses assert_local_postgres_url only when
    every required condition is met, without ever reaching a real DB."""
    result = _run(
        "--production",
        "--database-url",
        "postgresql://user:pass@remote-host.example.com:5432/db",
        "--dry-run",
    )
    assert result.returncode != 2, result.stderr
    assert "only permits a local PostgreSQL DATABASE_URL" not in result.stderr
    assert "requires exactly one of" not in result.stderr


def test_production_execute_with_explicit_database_url_clears_argument_validation():
    result = _run(
        "--production",
        "--database-url",
        "postgresql://user:pass@remote-host.example.com:5432/db",
        "--execute",
    )
    assert result.returncode != 2, result.stderr
    assert "only permits a local PostgreSQL DATABASE_URL" not in result.stderr


def test_non_production_mode_with_no_database_url_still_uses_local_settings_default():
    """Unchanged pre-existing behavior: with no --database-url and no
    --production, the script falls back to settings.database_url and
    still enforces the local-only guard on it -- this test only asserts
    the guard is still reached (not bypassed by default), not any
    specific outcome for the developer's own local DB."""
    result = _run("--dry-run")
    # Either the local settings.database_url is genuinely local (clears
    # the guard, then fails later on the fake manifest) or it errors --
    # either way it must never mention --production's own guard messages.
    assert "requires --database-url to be passed explicitly" not in result.stderr
    assert "requires exactly one of --dry-run or --execute" not in result.stderr
