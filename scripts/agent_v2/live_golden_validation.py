"""Phase 4 STEP 2 (V2 RC1 validation): run all 101 golden queries against the
REAL Railway production HTTP path (``POST /api/v1/agent/v2/orchestrate``),
using a real canary-account JWT. No mocking, no in-process shortcuts -- this
hits the actual deployed RC1 exactly the way a real client would, through the
canary allowlist mechanism (``AGENT_CANARY_ALLOWLIST``), with production's
real rollout percentage (5%) left untouched.

Source of the 101 queries: the same fixed golden set BUILD-24C/24J/24M used
(``data pharmacy/reports/agent-architecture/34-build-24c-golden-set-results.json``)
-- reuses only query text + expected_*/target_patient_id fields, never the old
actual_answer/verdict.

Each row's own ``target_patient_id`` is used verbatim in the request body
(not hardcoded to one patient) -- 2 of the 101 rows (query_id 96, 100)
deliberately target ``agent-v2-canary-patient-2`` (a bare patient row with no
account of its own) specifically to exercise the cross-patient authorization
denial path (``require_agent_patient_access``), expecting HTTP 403. This
script does not grade PASS/FAIL_DEFECT/FAIL_SCOPE itself (that requires
judgment against each row's ``expected_criteria``, done by hand afterward,
exactly as BUILD-24C/24J/24M did) -- it only collects raw, faithful results.

Usage::

    $env:AGENT_V2_CANARY_JWT = "<JWT for agent-v2-canary-patient1-account>"
    python scripts/agent_v2/live_golden_validation.py [--limit N] [--ids "1,2,3"] [--out path]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

GOLDEN_SOURCE = Path(__file__).resolve().parents[2] / "data pharmacy" / "reports" / "agent-architecture" / "34-build-24c-golden-set-results.json"
BASE_URL = "https://vmec-04be-production.up.railway.app"
ENDPOINT = "/api/v1/agent/v2/orchestrate"


def _run_one(client: httpx.Client, jwt: str, query: dict, *, index: int, total: int) -> dict:
    started = time.monotonic()
    payload = {
        "patient_id": query["target_patient_id"],
        "message": query["query"],
        "conversation_id": f"live-golden:{query['query_id']}",
        "session_id": str(uuid.uuid4()),
    }
    row = {
        "query_id": query["query_id"],
        "query": query["query"],
        "expected_category": query.get("expected_category"),
        "expected_technical_branch": query.get("expected_technical_branch"),
        "expected_difficulty": query.get("expected_difficulty"),
        "expected_safety_level": query.get("expected_safety_level"),
        "expected_criteria": query.get("expected_criteria"),
        "target_patient_id": query["target_patient_id"],
    }
    try:
        resp = client.post(
            ENDPOINT,
            json=payload,
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=120.0,
        )
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        row["http_status"] = resp.status_code
        row["latency_ms"] = elapsed_ms
        if resp.status_code == 200:
            body = resp.json()
            row.update(
                {
                    "agent_status": body.get("status"),
                    "intent": body.get("intent"),
                    "tools_used": body.get("tools", []),
                    "safety_disposition": body.get("safety_disposition"),
                    "handoff_id": body.get("handoff_id"),
                    "citations": body.get("citations", []),
                    "trace_id": body.get("trace_id"),
                    "agent_run_id": body.get("agent_run_id"),
                    "actual_answer": body.get("reply"),
                }
            )
        else:
            row["actual_answer"] = None
            try:
                row["error_detail"] = resp.json().get("detail")
            except Exception:  # noqa: BLE001 -- non-JSON error body, keep raw text
                row["error_detail"] = resp.text[:500]
    except httpx.RequestError as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        row["http_status"] = None
        row["latency_ms"] = elapsed_ms
        row["agent_status"] = "TRANSPORT_ERROR"
        row["actual_answer"] = f"{type(exc).__name__}: {exc}"

    print(
        f"[{index}/{total}] id={row['query_id']} http={row.get('http_status')} "
        f"status={row.get('agent_status')} intent={row.get('intent')} latency={row['latency_ms']}ms",
        flush=True,
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--ids", type=str, default=None, help="comma-separated query_id list, overrides --start/--limit")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    jwt = os.environ.get("AGENT_V2_CANARY_JWT")
    if not jwt:
        print("ERROR: set $env:AGENT_V2_CANARY_JWT to a valid JWT before running.", file=sys.stderr)
        return 2

    with GOLDEN_SOURCE.open(encoding="utf-8") as f:
        source = json.load(f)
    id_filter = {int(x) for x in args.ids.split(",")} if args.ids else None

    def _wanted(query_id: int) -> bool:
        if id_filter is not None:
            return query_id in id_filter
        return query_id >= args.start

    queries = [
        {
            "query_id": row["query_id"],
            "query": row["query"],
            "expected_category": row.get("expected_category"),
            "expected_technical_branch": row.get("expected_technical_branch"),
            "expected_difficulty": row.get("expected_difficulty"),
            "expected_safety_level": row.get("expected_safety_level"),
            "expected_criteria": row.get("expected_criteria"),
            "target_patient_id": row["target_patient_id"],
        }
        for row in source
        if _wanted(row["query_id"])
    ]
    if args.limit is not None:
        queries = queries[: args.limit]

    results = []
    total = len(queries)
    with httpx.Client(base_url=BASE_URL) as client:
        for i, query in enumerate(queries, start=1):
            results.append(_run_one(client, jwt, query, index=i, total=total))

    out_path = Path(args.out) if args.out else Path(__file__).resolve().parents[2] / "data pharmacy" / "reports" / "agent-architecture" / "49-build-24o-phase4-railway-golden-results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(results)} results to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
