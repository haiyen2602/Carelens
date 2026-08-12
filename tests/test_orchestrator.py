"""Phase 5 - test bat buoc (rui ro cao nhat, nhac lai truoc khi code): safety
layer phai chay THAT SONG SONG voi luong chinh va co the cat ngang GIUA
CHUNG, khong phai test kieu "goi safety truoc, gan ket qua, roi kiem tra
nhanh" (khong chung minh duoc hanh vi race-condition that).

Dung asyncio.Event de EP chinh xac thoi diem safety_task tra ve redflag xay
ra GIUA node 2 va node 3 - khong dua vao may man cua wall-clock timing (vd
asyncio.sleep(x) roi doan), ma dieu phoi tuong minh: node 3 chi bat dau SAU
khi node 2 da bao "toi bat dau roi" cho safety task, va safety task chi tra
ve SAU khi nhan tin hieu do - dam bao thu tu quan sat duoc, khong flaky.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from backend.agents.orchestrator import run_conversation  # noqa: E402
from backend.services.escalation import (  # noqa: E402
    GENERIC_OVERLAY_MESSAGE,
    OVERDOSE_OVERLAY_MESSAGE,
    SYMPTOM_OVERLAY_MESSAGE,
)
from backend.services.safety import SafetyFlag  # noqa: E402


def _make_state():
    return {"patient_id": "p1", "dose_event_id": None, "utterance": "test", "trace": []}


async def _node(name: str, event_to_set: asyncio.Event | None = None, sleep_s: float = 0.0):
    """Node gia: ghi trace 1 entry ten `name`. Neu co event_to_set, SET no
    NGAY KHI BAT DAU chay (khong phai luc ket thuc) - de safety task biet
    chinh xac "node nay da bat dau" ma khong can doan thoi gian."""

    async def node_fn(state: dict) -> dict:
        if event_to_set is not None:
            event_to_set.set()
        if sleep_s:
            await asyncio.sleep(sleep_s)
        return {"trace": [*state.get("trace", []), {"step": name}]}

    return node_fn


@pytest.mark.asyncio
async def test_redflag_arriving_between_node2_and_node3_stops_before_node3():
    """Kich ban dung nhu yeu cau: redflag toi SAU KHI node 2 (vd retrieval)
    da chay xong NHUNG TRUOC KHI node 3 (vd answer_generation) chay xong -
    dieu phoi bang asyncio.Event de dam bao thu tu chinh xac, khong doan gio."""
    node2_started = asyncio.Event()

    node1 = await _node("node1")
    node2 = await _node("node2", event_to_set=node2_started, sleep_s=0.05)
    node3 = await _node("node3")

    async def delayed_redflag_safety_check(utterance: str) -> SafetyFlag:
        # Cho den khi node2 da BAT DAU (tuc node1 chac chan da chay xong,
        # vi node chay tuan tu) - roi tra ve redflag TRUOC KHI node2 kip xong
        # (node2 dang sleep 0.05s, o day chi cho 0.01s roi tra loi ngay).
        await node2_started.wait()
        await asyncio.sleep(0.01)
        return SafetyFlag(is_redflag=True, matched_group="clinical", matched_keyword="đau ngực", source="keyword")

    result = await run_conversation(
        _make_state(),
        nodes=[node1, node2, node3],
        safety_check=delayed_redflag_safety_check,
    )

    steps_in_trace = [e.get("step") for e in result["trace"]]

    assert "node1" in steps_in_trace, "node1 phai da chay xong (chay truoc khi redflag toi)"
    assert "node3" not in steps_in_trace, (
        "node3 (vd answer_generation) KHONG duoc chay - redflag da toi truoc do, "
        "neu node3 van chay tuc safety layer khong that su cat ngang duoc"
    )
    assert "safety_layer" in steps_in_trace, "phai co entry safety_layer the hien redflag da kich hoat"
    assert result["safety_flag"] is True
    assert result["severity"] == "Nguy hiểm"

    safety_entry = next(e for e in result["trace"] if e["step"] == "safety_layer")
    assert safety_entry["interrupted_after_step"] == "node2", (
        f"trace phai the hien dung diem dung la SAU node2 - thuc te: {safety_entry['interrupted_after_step']!r}"
    )


@pytest.mark.asyncio
async def test_no_redflag_runs_all_nodes_to_completion():
    """Doi chung: khi safety_check khong bao gio redflag, ca 3 node phai
    chay het, tranh truong hop test tren pass "an gian" vi logic luon dung
    som bat ke ket qua safety the nao."""
    node1 = await _node("node1")
    node2 = await _node("node2")
    node3 = await _node("node3")

    async def clean_safety_check(utterance: str) -> SafetyFlag:
        await asyncio.sleep(0.001)
        return SafetyFlag(is_redflag=False, matched_group=None, matched_keyword=None, source="keyword")

    result = await run_conversation(
        _make_state(), nodes=[node1, node2, node3], safety_check=clean_safety_check
    )

    steps_in_trace = [e.get("step") for e in result["trace"]]
    assert steps_in_trace == ["node1", "node2", "node3", "safety_layer"]
    assert result["safety_flag"] is False


@pytest.mark.asyncio
async def test_redflag_arriving_before_any_node_starts_stops_immediately():
    """Truong hop bien: redflag co san ngay tu dau (khong delay) - khong node
    nao trong luong chinh duoc chay."""
    node1 = await _node("node1")
    node2 = await _node("node2")

    async def instant_redflag(utterance: str) -> SafetyFlag:
        return SafetyFlag(is_redflag=True, matched_group="overdose_risk", matched_keyword="10 viên", source="keyword")

    result = await run_conversation(_make_state(), nodes=[node1, node2], safety_check=instant_redflag)

    steps_in_trace = [e.get("step") for e in result["trace"]]
    assert steps_in_trace == ["safety_layer"]
    safety_entry = result["trace"][0]
    assert safety_entry["interrupted_after_step"] is None


@pytest.mark.asyncio
async def test_redflag_triggers_shared_escalation_handler_not_a_separate_one():
    """Diem bat buoc (code review Phase 5b, 2026-08-08): safety_layer redflag
    va SEVERITY -> LEVEL = "Nguy hiểm" (xem test_dose_confirmation_nodes.py)
    PHAI cung goi 1 ham escalate dung chung (backend/services/escalation.py),
    khong duoc code rieng 2 lan. Truoc fix nay, redflag chi set response/
    severity ma KHONG bao gio thuc su goi escalate_fn - BR-3.5 (gui nguoi
    than + bac si) khong duoc thuc hien tren duong nay."""
    calls: list = []

    async def spy_escalate(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        calls.append((target, patient_id, dose_event_id, severity, urgent, trigger, reason))

    async def instant_redflag(utterance: str) -> SafetyFlag:
        return SafetyFlag(is_redflag=True, matched_group="clinical", matched_keyword="đau ngực", source="keyword")

    result = await run_conversation(
        {"patient_id": "p1", "dose_event_id": "dose-9", "utterance": "test", "trace": []},
        nodes=[],
        safety_check=instant_redflag,
        escalate_fn=spy_escalate,
    )

    assert {c[0] for c in calls} == {"family", "doctor"}, "phai goi CA family LAN doctor"
    assert all(c[1] == "p1" and c[2] == "dose-9" and c[4] is True and c[5] == "safety_redflag" for c in calls)
    assert all(c[6] for c in calls), "reason khong duoc rong - phai giai thich duoc vi sao escalate"
    safety_entry = result["trace"][0]
    assert set(safety_entry["escalated_to"]) == {"family", "doctor"}


@pytest.mark.asyncio
async def test_redflag_without_escalate_fn_does_not_crash_and_marks_not_escalated():
    """escalate_fn la optional (None mac dinh, vd test/chua wiring Phase 6) -
    khong duoc crash, va trace phai the hien trung thuc la CHUA escalate
    (escalated_to rong), khong duoc gia vo da lam."""

    async def instant_redflag(utterance: str) -> SafetyFlag:
        return SafetyFlag(is_redflag=True, matched_group="clinical", matched_keyword="đau ngực", source="keyword")

    result = await run_conversation(_make_state(), nodes=[], safety_check=instant_redflag)

    safety_entry = result["trace"][0]
    assert safety_entry["escalated_to"] == []


@pytest.mark.asyncio
async def test_redflag_partial_escalation_failure_is_visible_in_trace_not_hidden():
    """Code review 2026-08-08: neu 1 kenh (vd doctor) that bai luc escalate,
    trace PHAI the hien ro kenh nao that bai va vi sao - khong duoc gop
    chung "da escalate" nhu truoc, vi voi cap cuu biet dung kenh nao loi
    quan trong hon RAG rat nhieu (can goi lai thu cong neu khong ai nhan
    duoc canh bao)."""

    async def doctor_fails(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        if target == "doctor":
            raise RuntimeError("push doctor that bai (mo phong)")

    async def instant_redflag(utterance: str) -> SafetyFlag:
        return SafetyFlag(is_redflag=True, matched_group="clinical", matched_keyword="đau ngực", source="keyword")

    result = await run_conversation(_make_state(), nodes=[], safety_check=instant_redflag, escalate_fn=doctor_fails)

    safety_entry = result["trace"][0]
    assert safety_entry["escalated_to"] == ["family"], "family thanh cong khong duoc bi an di"
    assert "doctor" in safety_entry["escalation_failed"], "doctor that bai phai hien ro trong trace, khong duoc giau"
    assert "that bai" in safety_entry["escalation_failed"]["doctor"] or safety_entry["escalation_failed"]["doctor"]

@pytest.mark.asyncio
async def test_overdose_risk_matched_group_uses_overdose_overlay_message():
    """Vong 2 (chatbot-rag-design.md muc 7.1) - matched_group="overdose_risk"
    (BR-6.7/6.8, vd "toi co 10 vien uong het") PHAI dung OVERDOSE_OVERLAY_
    MESSAGE, KHAC voi nhom trieu chung lam sang."""

    async def instant_overdose_redflag(utterance: str) -> SafetyFlag:
        return SafetyFlag(is_redflag=True, matched_group="overdose_risk", matched_keyword="10 viên", source="keyword")

    result = await run_conversation(_make_state(), nodes=[], safety_check=instant_overdose_redflag)

    assert result["response"] == OVERDOSE_OVERLAY_MESSAGE
    assert result["response"] != SYMPTOM_OVERLAY_MESSAGE


@pytest.mark.asyncio
async def test_clinical_matched_group_uses_symptom_overlay_message():
    """matched_group="clinical" (kho tho, dau nguc...) PHAI dung SYMPTOM_
    OVERLAY_MESSAGE, khac OVERDOSE_OVERLAY_MESSAGE cua nhom lieu dung."""

    async def instant_clinical_redflag(utterance: str) -> SafetyFlag:
        return SafetyFlag(is_redflag=True, matched_group="clinical", matched_keyword="đau ngực", source="keyword")

    result = await run_conversation(_make_state(), nodes=[], safety_check=instant_clinical_redflag)

    assert result["response"] == SYMPTOM_OVERLAY_MESSAGE
    assert result["response"] != OVERDOSE_OVERLAY_MESSAGE


@pytest.mark.asyncio
async def test_llm_only_redflag_without_matched_group_uses_generic_overlay():
    """Sua 2026-08-09 (review) - matched_group=None (LLM-only detection,
    khong khop keyword group nao) PHAI dung GENERIC_OVERLAY_MESSAGE rieng,
    KHONG duoc ep vao overdose/symptom (he thong chua biet day la loai nguy
    hiem gi, gan nham nhan cu the se dua thong tin sai nhung nghe cu the)."""

    async def instant_llm_redflag(utterance: str) -> SafetyFlag:
        return SafetyFlag(is_redflag=True, matched_group=None, matched_keyword=None, source="llm")

    result = await run_conversation(_make_state(), nodes=[], safety_check=instant_llm_redflag)

    assert result["response"] == GENERIC_OVERLAY_MESSAGE
    assert result["response"] not in (OVERDOSE_OVERLAY_MESSAGE, SYMPTOM_OVERLAY_MESSAGE)


# ---------------------------------------------------------------------------
# Vong 3 (phan hoi review 2026-08-12) - "Trung bình" o 2 category self_harm/
# clinical_symptom: escalate KHONG khan CHI kenh family + 1 cau ghi nhan nhe,
# KHONG cat luong chinh (khac han is_redflag=True o tren).
# ---------------------------------------------------------------------------


async def _medium_safety_check(category: str):
    async def check(utterance: str) -> SafetyFlag:
        return SafetyFlag(
            is_redflag=False,
            matched_group=None,
            matched_keyword=None,
            source="llm",
            level="Trung bình",
            llm_category=category,
            llm_reasoning="test",
        )

    return check


@pytest.mark.asyncio
async def test_medium_self_harm_escalates_family_only_and_appends_acknowledgment():
    calls = []

    async def recording_escalate_fn(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        calls.append({"target": target, "severity": severity, "urgent": urgent})

    async def set_response_node(state: dict) -> dict:
        return {"response": "Câu trả lời bình thường.", "trace": [*state.get("trace", []), {"step": "answer_generation"}]}

    result = await run_conversation(
        _make_state(),
        nodes=[set_response_node],
        safety_check=await _medium_safety_check("self_harm"),
        escalate_fn=recording_escalate_fn,
    )

    # Luong chinh KHONG bi cat - response goc van con, chi duoc GHEP THEM
    # cau ghi nhan, khong bi THAY THE.
    assert "Câu trả lời bình thường." in result["response"]
    assert "Capy đã ghi nhận" in result["response"]
    assert result["safety_flag"] is False  # KHONG phai overlay khan cap

    assert len(calls) == 1
    assert calls[0]["target"] == "family"  # CHI family, khong goi "doctor"
    assert calls[0]["urgent"] is False
    assert calls[0]["severity"] == "Trung bình"


@pytest.mark.asyncio
async def test_medium_wrong_category_does_not_escalate_but_still_acknowledges():
    """BUG THAT sua 2026-08-12 (phan hoi review lan 2): ban dau (a) va (c)
    bi gop chung 1 dieu kien, khien category ngoai {self_harm,
    clinical_symptom} (vd wrong_drug - vua duoc _CATEGORY_LEVEL_FLOOR nang
    len toi thieu Trung bình) IM LANG HOAN TOAN - quay lai dung bug rong-
    response. Dung: khong escalate (chinh sach (a) - dung gioi han pham vi
    nay) NHUNG VAN phai co cau ghi nhan (chinh sach (c) - ap dung cho MOI
    "Trung bình", khong chi 2 category duoc escalate)."""
    calls = []

    async def recording_escalate_fn(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        calls.append(target)

    async def set_response_node(state: dict) -> dict:
        return {"response": "Câu trả lời bình thường.", "trace": [*state.get("trace", []), {"step": "x"}]}

    result = await run_conversation(
        _make_state(),
        nodes=[set_response_node],
        safety_check=await _medium_safety_check("wrong_drug"),
        escalate_fn=recording_escalate_fn,
    )

    assert calls == [], "wrong_drug khong thuoc pham vi escalate (a)"
    assert "Câu trả lời bình thường." in result["response"]
    assert "Capy đã ghi nhận" in result["response"], "van phai co ghi nhan (c) du khong escalate"


@pytest.mark.asyncio
async def test_medium_acknowledgment_works_without_escalate_fn():
    """escalate_fn=None (test/chua wiring) - van ghep duoc cau ghi nhan,
    khong crash vi thieu escalate_fn."""

    async def set_response_node(state: dict) -> dict:
        return {"response": "Câu trả lời bình thường.", "trace": [*state.get("trace", []), {"step": "x"}]}

    result = await run_conversation(
        _make_state(),
        nodes=[set_response_node],
        safety_check=await _medium_safety_check("clinical_symptom"),
        escalate_fn=None,
    )

    assert "Capy đã ghi nhận" in result["response"]


@pytest.mark.asyncio
async def test_medium_escalate_failure_does_not_crash_or_block_acknowledgment():
    async def broken_escalate_fn(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        raise RuntimeError("DB loi")

    async def set_response_node(state: dict) -> dict:
        return {"response": "Câu trả lời bình thường.", "trace": [*state.get("trace", []), {"step": "x"}]}

    result = await run_conversation(
        _make_state(),
        nodes=[set_response_node],
        safety_check=await _medium_safety_check("self_harm"),
        escalate_fn=broken_escalate_fn,
    )

    assert "Capy đã ghi nhận" in result["response"]  # van co ghi nhan du escalate loi


@pytest.mark.asyncio
async def test_nhe_level_does_not_get_medium_acknowledgment_or_escalate():
    """Regression - "Nhẹ" (khac "Trung bình") KHONG duoc kich hoat ca ghi
    nhan lan escalate, du category la self_harm (co the xay ra o category
    khac ngoai self_harm/wrong_drug, 2 category duy nhat co floor)."""
    calls = []

    async def recording_escalate_fn(target, patient_id, dose_event_id, severity, urgent, trigger, reason):
        calls.append(target)

    async def nhe_safety_check(utterance: str) -> SafetyFlag:
        return SafetyFlag(
            is_redflag=False,
            matched_group=None,
            matched_keyword=None,
            source="llm",
            level="Nhẹ",
            llm_category="severe_reaction",
            llm_reasoning="test",
        )

    async def set_response_node(state: dict) -> dict:
        return {"response": "Câu trả lời bình thường.", "trace": [*state.get("trace", []), {"step": "x"}]}

    result = await run_conversation(
        _make_state(), nodes=[set_response_node], safety_check=nhe_safety_check, escalate_fn=recording_escalate_fn
    )

    assert calls == []
    assert result["response"] == "Câu trả lời bình thường."

