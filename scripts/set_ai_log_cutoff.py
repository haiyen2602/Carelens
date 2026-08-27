#!/usr/bin/env python3
"""Create the local timestamp that excludes earlier AI logs from submission."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path


def write_cutoff(log_dir: Path, *, force: bool = False) -> Path:
    """Write an activation marker without resetting an existing boundary by default."""
    log_dir.mkdir(parents=True, exist_ok=True)
    marker = log_dir / "submit-not-before.json"
    if marker.exists() and not force:
        return marker

    payload = {
        "version": 1,
        "not_before": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "reason": "Exclude AI log history created before local activation",
    }
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, marker)
    return marker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing cutoff. This can exclude newer unsent logs.",
    )
    args = parser.parse_args()
    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    marker = write_cutoff(log_dir, force=args.force)
    print(f"[ai-log] Submission cutoff ready: {marker}")


if __name__ == "__main__":
    main()
