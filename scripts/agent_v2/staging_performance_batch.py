"""BUILD-20: batch live-staging performance measurement.

Fires N requests per representative scenario against a live staging
deployment and reports P50/P95/P99 latency plus token/tool usage, so
"production hardening" performance claims are backed by more than one
sample per scenario (BUILD-19/19B's UAT was necessarily single-shot per
scenario; this is deliberately a batch). Makes no pass/fail assertions --
this is a measurement tool, not a test; the BUILD-20 report interprets the
numbers it prints.

Usage::

    PATIENT_JWT=... PATIENT1_ID=... \
    python scripts/agent_v2/staging_performance_batch.py --base-url https://<staging-be-host> --n 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _call(base_url: str, path: str, *, token: str, body: dict, timeout: float = 60.0):
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {token}")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            latency_ms = (time.perf_counter() - started) * 1000
            return response.status, (json.loads(raw) if raw else {}), latency_ms
    except urllib.error.HTTPError as error:
        latency_ms = (time.perf_counter() - started) * 1000
        raw = error.read()
        try:
            return error.code, json.loads(raw), latency_ms
        except json.JSONDecodeError:
            return error.code, {"detail": raw.decode("utf-8", errors="replace")}, latency_ms


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _run_scenario(base_url: str, name: str, *, token: str, body: dict, n: int) -> dict:
    latencies: list[float] = []
    statuses: list[str] = []
    reply_lens: list[int] = []
    tool_counts: list[int] = []
    http_errors = 0
    for i in range(n):
        status_code, response, latency_ms = _call(base_url, "/api/v1/agent/v2/orchestrate", token=token, body=body)
        if status_code != 200:
            http_errors += 1
            print(json.dumps({"scenario": name, "run": i, "http_status": status_code, "detail": response}, ensure_ascii=False))
            continue
        latencies.append(latency_ms)
        statuses.append(response.get("status") or "")
        reply_lens.append(len(response.get("reply") or ""))
        tool_counts.append(len(response.get("tools") or []))
    summary = {
        "scenario": name,
        "n": n,
        "http_errors": http_errors,
        "p50_ms": round(_percentile(latencies, 0.50), 1),
        "p95_ms": round(_percentile(latencies, 0.95), 1),
        "p99_ms": round(_percentile(latencies, 0.99), 1),
        "min_ms": round(min(latencies), 1) if latencies else None,
        "max_ms": round(max(latencies), 1) if latencies else None,
        "statuses": {s: statuses.count(s) for s in set(statuses)},
        "empty_replies": sum(1 for length in reply_lens if length == 0),
        "avg_tool_calls": round(sum(tool_counts) / len(tool_counts), 2) if tool_counts else None,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--n", type=int, default=10, help="Requests per scenario")
    args = parser.parse_args()

    patient_jwt = os.environ["PATIENT_JWT"]
    patient1 = os.environ["PATIENT1_ID"]

    scenarios = [
        ("drug_information", {"patient_id": patient1, "message": "Cho toi biet cong dung cua thuoc paracetamol"}),
        ("today_doses", {"patient_id": patient1, "message": "Hom nay toi can uong nhung thuoc gi"}),
        ("prescription_multi_tool", {"patient_id": patient1, "message": "Don thuoc va lich uong thuoc cua toi hien tai the nao"}),
        ("rag_query", {"patient_id": patient1, "message": "Tac dung phu thuong gap cua thuoc giam dau la gi"}),
    ]

    all_summaries = []
    for name, body in scenarios:
        summary = _run_scenario(args.base_url, name, token=patient_jwt, body=body, n=args.n)
        all_summaries.append(summary)

    print("BEGIN_SUMMARY_TABLE")
    for s in all_summaries:
        print(json.dumps(s, ensure_ascii=False))
    print("END_SUMMARY_TABLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
