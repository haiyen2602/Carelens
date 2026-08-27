#!/usr/bin/env python3
"""
Submit .ai-log/session.jsonl to grading server.
Called by git pre-push hook or manually.

After a successful submit, the live log is rotated:
  - Moved into .ai-log/archive/YYYY-MM-DD.jsonl (appended, never overwritten)
  - The live session.jsonl is recreated empty by the next hook write

If the POST fails, the pending file is restored so nothing is lost.
"""

import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

SERVER_URL = os.environ.get("AI_LOG_SERVER", "")
API_KEY = os.environ.get("AI_LOG_API_KEY", "")
LOG_DIR = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
LOG_FILE = LOG_DIR / "session.jsonl"
ARCHIVE_DIR = LOG_DIR / "archive"
CUTOFF_FILE = LOG_DIR / "submit-not-before.json"

# Match server-side MAX_BATCH_ENTRIES so we never get a 422.
# If the local file has more than this, we submit the oldest BATCH_LIMIT
# and leave the rest for the next push.
BATCH_LIMIT = 500


class CutoffError(ValueError):
    """Raised when a configured submission cutoff cannot be trusted."""


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and normalize it to UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CutoffError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _load_cutoff() -> datetime | None:
    """Load the local opt-in boundary; fail closed if the marker is invalid."""
    if not CUTOFF_FILE.exists():
        return None
    try:
        payload = json.loads(CUTOFF_FILE.read_text(encoding="utf-8"))
        value = payload["not_before"]
        if not isinstance(value, str) or not value.strip():
            raise CutoffError("not_before must be a non-empty string")
        return _parse_timestamp(value)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CutoffError(f"invalid cutoff file {CUTOFF_FILE}: {exc}") from exc


def _eligible_for_submission(entry: dict, cutoff: datetime | None) -> bool:
    """Return whether an entry is new enough to leave the local machine."""
    if cutoff is None:
        return True
    timestamp = entry.get("ts")
    if not isinstance(timestamp, str):
        return False
    try:
        return _parse_timestamp(timestamp) >= cutoff
    except (TypeError, ValueError):
        return False


def _archive_lines(lines: list[str]) -> None:
    """Append selected raw lines to today's archive without overwriting data."""
    if not lines:
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    archive_file = ARCHIVE_DIR / f"{today}.jsonl"
    with open(archive_file, "a", encoding="utf-8") as destination:
        destination.writelines(lines)


def _restore_pending(pending: Path) -> None:
    """Failure path: put pending back at LOG_FILE so the next push retries.
    If hook wrote new entries to LOG_FILE in the meantime, prepend pending."""
    if not pending.exists():
        return
    if LOG_FILE.exists():
        # Concat: pending (older) + LOG_FILE (newer) → LOG_FILE
        tmp = LOG_FILE.with_suffix(".merge.jsonl")
        with open(tmp, "wb") as out:
            with open(pending, "rb") as a:
                shutil.copyfileobj(a, out)
            with open(LOG_FILE, "rb") as b:
                shutil.copyfileobj(b, out)
        os.replace(tmp, LOG_FILE)
        pending.unlink()
    else:
        pending.rename(LOG_FILE)


def main():
    if not SERVER_URL:
        print("[ai-log] AI_LOG_SERVER not set — skipping submission.", file=sys.stderr)
        sys.exit(0)

    if not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0:
        print("[ai-log] No logs to submit.", file=sys.stderr)
        sys.exit(0)

    try:
        cutoff = _load_cutoff()
    except CutoffError as exc:
        print(f"[ai-log] {exc} — submission skipped; logs kept locally.", file=sys.stderr)
        sys.exit(0)

    # Atomic rename closes the race window: hook writes that arrive after this
    # land in a fresh LOG_FILE, not in the batch we're about to POST.
    pending = LOG_FILE.with_name(f"session.pending.{int(time.time())}.jsonl")
    try:
        LOG_FILE.rename(pending)
    except FileNotFoundError:
        print("[ai-log] No logs to submit.", file=sys.stderr)
        sys.exit(0)

    entries = []
    leftover_lines = []
    archive_lines = []
    excluded_count = 0
    with open(pending, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError:
                archive_lines.append(line)
                continue
            if not isinstance(entry, dict) or not _eligible_for_submission(entry, cutoff):
                excluded_count += 1
                archive_lines.append(line)
                continue
            if len(entries) >= BATCH_LIMIT:
                leftover_lines.append(line)
                continue
            entries.append(entry)
            archive_lines.append(line)

    if not entries:
        # Old or malformed entries stay local in archive and never reach the server.
        _archive_lines(archive_lines)
        pending.unlink()
        print(
            f"[ai-log] No eligible logs to submit; archived {excluded_count} older entries locally.",
            file=sys.stderr,
        )
        sys.exit(0)

    payload = json.dumps({"entries": entries}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(
        SERVER_URL,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[ai-log] Submitted {len(entries)} entries → {resp.status}", file=sys.stderr)
    except urllib.error.URLError as e:
        # Failure: restore the whole pending (including leftover) for next push.
        _restore_pending(pending)
        print(f"[ai-log] Submit failed: {e} — logs kept locally.", file=sys.stderr)
        sys.exit(0)  # Don't block push on server error

    # Success: archive submitted and excluded lines, then handle eligible leftovers.
    _archive_lines(archive_lines)
    pending.unlink()

    if leftover_lines:
        # More than BATCH_LIMIT entries existed; put the rest back so the
        # next push picks them up.
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.writelines(leftover_lines)
        print(
            f"[ai-log] {len(leftover_lines)} entries deferred to next push.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
