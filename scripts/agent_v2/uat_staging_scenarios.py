"""BUILD-19: controlled staging UAT scenario driver.

Runs the main Agent V2 flows against a live staging deployment and prints
one JSON line per call (status, latency, citations, safety, handoff,
tool trace) plus the full response body, so a human/tester reviewing this
build's report can see exactly what happened. Makes no assertions itself
(this is a UAT run, not a pass/fail gate) -- issue triage happens in the
BUILD-19 report after reviewing this output plus direct database/log checks.

Usage::

    DOCTOR_JWT=... CAREGIVER_JWT=... PATIENT_JWT=... \
    PATIENT1_ID=... PATIENT2_ID=... MISSED_DOSE_GROUP_ID=... \
    python scripts/agent_v2/uat_staging_scenarios.py --base-url https://<staging-be-host>
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


def _call(base_url: str, path: str, *, token: str | None, body: dict, timeout: float = 60.0):
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    if token:
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


def _run(base_url: str, name: str, *, token: str, body: dict) -> dict:
    status, response, latency_ms = _call(base_url, "/api/v1/agent/v2/orchestrate", token=token, body=body)
    record = {
        "scenario": name,
        "http_status": status,
        "latency_ms": round(latency_ms, 1),
        "agent_status": response.get("status"),
        "intent": response.get("intent"),
        "tools": response.get("tools"),
        "citations": response.get("citations"),
        "safety_disposition": response.get("safety_disposition"),
        "handoff_id": response.get("handoff_id"),
        "trace_id": response.get("trace_id"),
        "agent_run_id": response.get("agent_run_id"),
        "reply": response.get("reply"),
        "reply_len": len(response.get("reply") or ""),
    }
    print(json.dumps(record, ensure_ascii=False))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    base = args.base_url

    patient_jwt = os.environ["PATIENT_JWT"]
    caregiver_jwt = os.environ["CAREGIVER_JWT"]
    patient1 = os.environ["PATIENT1_ID"]
    patient2 = os.environ["PATIENT2_ID"]
    missed_dose_id = os.environ.get("MISSED_DOSE_GROUP_ID")
    pending_dose_id = os.environ.get("PENDING_DOSE_GROUP_ID")

    conv_id = "uat-memory-conversation-1"
    sess_id = "uat-memory-session-1"

    # 1. Drug information
    _run(base, "drug_information", token=patient_jwt, body={
        "patient_id": patient1, "message": "Cho toi biet cong dung cua thuoc paracetamol",
        "conversation_id": conv_id, "session_id": sess_id,
    })

    # 2. RAG (open semantic question)
    _run(base, "rag_query", token=patient_jwt, body={
        "patient_id": patient1, "message": "Tac dung phu thuong gap cua thuoc giam dau la gi",
    })

    # 3. Memory recall (same conversation as #1; refers back implicitly)
    _run(base, "memory_recall_followup", token=patient_jwt, body={
        "patient_id": patient1, "message": "Thuoc do uong truoc hay sau an",
        "conversation_id": conv_id, "session_id": sess_id,
    })

    # 4. Patient dose query
    _run(base, "patient_dose_query", token=patient_jwt, body={
        "patient_id": patient1, "message": "Hom nay toi can uong nhung thuoc gi",
    })

    # 5. Vinmec Web (recorded as DEGRADED per BUILD-18B, not hidden)
    _run(base, "vinmec_web", token=patient_jwt, body={
        "patient_id": patient1, "message": "Tim tren Vinmec thong tin ve benh tieu duong",
    })

    # 6. Safety SAFE (real MISSED occurrence with a reviewed low-risk policy)
    if missed_dose_id:
        _run(base, "safety_safe", token=patient_jwt, body={
            "patient_id": patient1, "message": "Toi quen uong thuoc sang nay", "dose_id": missed_dose_id,
        })
    else:
        print(json.dumps({"scenario": "safety_safe", "skipped": "no MISSED_DOSE_GROUP_ID provided"}))

    # 7. Safety unresolved -> fail-closed to Doctor Handoff (a still-PENDING dose cannot be assessed as missed)
    if pending_dose_id:
        _run(base, "safety_unresolved_pending_dose", token=patient_jwt, body={
            "patient_id": patient1, "message": "Toi quen uong thuoc trua nay", "dose_id": pending_dose_id,
        })

    # 8. Doctor Handoff (bypasses Safety Domain; dosage-change request)
    _run(base, "doctor_handoff", token=patient_jwt, body={
        "patient_id": patient1, "message": "Toi muon tang lieu thuoc len gap doi",
    })

    # 9. Cross-patient authorization denial (caregiver not linked to patient2)
    _run(base, "cross_patient_denial", token=caregiver_jwt, body={
        "patient_id": patient2, "message": "xin chao",
    })

    # 10. Prescription query
    _run(base, "prescription_query", token=patient_jwt, body={
        "patient_id": patient1, "message": "Don thuoc hien tai cua toi co gi",
    })

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
