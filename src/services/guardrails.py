"""AI Safety Guardrails (vong 2, chatbot-rag-design.md muc 12) - bao ve HE
THONG khoi bi thao tung/khai thac (injection, ro ri du lieu), KHAC voi
`src/services/safety.py` (bao ve BENH NHAN khoi nguy hiem y te) - 2 lop DOC
LAP, khong lop nao thay the lop kia (xem chatbot-rag-design.md muc 7 ghi
chu quan he).

12.1 Input guardrails: canonicalize + pattern-match injection TRUOC khi cho
utterance vao bat ky LLM call nao (kem intent_classification).
12.2 Output guardrails: redact secret pattern + chan ro ri patient_id cheo,
chay SAU khi co response, TRUOC khi tra ve nguoi dung."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 12.1 Input guardrails
# ---------------------------------------------------------------------------

INPUT_GUARDRAIL_REFUSAL_MESSAGE = (
    "Mình chỉ có thể hỗ trợ các câu hỏi liên quan tới thuốc và lịch uống thuốc của bạn. "
    "Bạn có thể hỏi lại theo hướng đó không?"
)


def _canonicalize(text: str) -> str:
    """Chuan hoa Unicode (NFKC - gop cac ky tu tuong duong ve 1 dang) + loai
    khoang trang an (zero-width space U+200B, BOM U+FEFF, zero-width joiner/
    non-joiner U+200C/200D) truoc khi so pattern - ne duoc kieu chen ky tu la
    giua tu de lach regex (vd "b​o qua" van phai khop "bo qua").

    GIOI HAN DA BIET: KHONG xu ly homoglyph (ky tu nhin giong nhau nhung khac
    codepoint, vd chu Cyrillic "а" trong "ignore" - can bang tra cuu rieng,
    ngoai pham vi vong nay) - ghi ro de khong ai tuong day la phong ve day
    du."""
    nfkc = unicodedata.normalize("NFKC", text)
    zero_width = "".join(("​", "﻿", "‌", "‍"))
    return re.sub(f"[{zero_width}]", "", nfkc)


def _strip_diacritics(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _normalize_for_pattern_match(text: str) -> str:
    return _strip_diacritics(_canonicalize(text)).lower()


# Moi pattern la 1 CUM TU/regex cu the, KHONG phai 1 tu don le de tranh khop
# nham cau hoi y te hop le (vd "quen" mot minh se khop ca "toi hay quen uong
# thuoc" - KHONG duoc dua vao list, chi cum du dai moi vao).
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # (category, regex - da qua _normalize_for_pattern_match: khong dau, thuong)
    ("ignore_instructions", r"bo qua (moi |tat ca )?(huong dan|chi thi|canh bao|quy tac)"),
    ("ignore_instructions", r"quen (vai tro|nhiem vu) cua (ban|minh)"),
    ("ignore_instructions", r"\bignore\s+(?:all\s+|any\s+|previous\s+)*(?:instructions?|rules?|warnings?)\b"),
    ("ignore_instructions", r"\bforget (your |the )?(role|rules?|instructions?)\b"),
    ("reveal_system_prompt", r"(doc lai|dich lai|cho (toi |minh )?xem) (system prompt|prompt he thong|huong dan goc)"),
    ("reveal_system_prompt", r"\b(repeat|reveal|show|print) (your |the )?(system prompt|instructions?)\b"),
    # THEM 2026-08-09 (muc 12.3, red-team phat hien): paraphrase "tom tat lai
    # ban duoc lap trinh de lam gi" lot qua 2 pattern reveal_system_prompt o
    # tren (khong dung tu "system prompt"/"huong dan goc" nhung CUNG y dinh).
    ("reveal_system_prompt", r"(tom tat lai|noi cho toi biet) .{0,20}(duoc lap trinh|lap trinh de lam)"),
    ("roleplay_bypass", r"gia vo (ban |minh )?khong phai (la )?chatbot y te"),
    ("roleplay_bypass", r"\bpretend (you'?re|you are) not a (medical )?chatbot\b"),
    ("roleplay_bypass", r"\bact as (if )?(you have no|there are no) (rules?|restrictions?)\b"),
    ("authority_impersonation", r"toi la (bac si|admin|quan tri vien|nguoi (phat trien|quan ly))\b.*(cho (toi|minh) xem|cho phep)"),
    ("authority_impersonation", r"\bi'?m (a |the )?(doctor|admin|developer)\b.*\bshow me\b"),
    # THEM 2026-08-09: paraphrase gian tiep hon "toi la admin" - tu nhan
    # "phu trach ky thuat" (khong phai tu khoa admin/developer ro rang) roi
    # hoi cach he thong xu ly du lieu benh nhan.
    ("authority_impersonation", r"(phu trach|quan ly) ky thuat.{0,60}(xu ly|luu tru|xem) du lieu (benh nhan|patient)"),
    ("other_patient_data", r"(cho|xem) (toi |minh )?(don thuoc|thong tin|du lieu) (cua )?benh nhan [a-z0-9]"),
    ("other_patient_data", r"\bshow me (patient|the prescription (of|for))\b"),
    # THEM 2026-08-09: paraphrase gian tiep - hoi lich/thong tin cua "benh
    # nhan khac" (khong neu ten/id cu the nhu 2 pattern tren, nhung van la
    # yeu cau du lieu nguoi khac ro rang).
    ("other_patient_data", r"(xem|biet|cho) .{0,25}(cua )?(nhung |cac )?benh nhan khac"),
]

_COMPILED_INJECTION_PATTERNS = [(category, re.compile(pattern)) for category, pattern in _INJECTION_PATTERNS]


@dataclass
class InputGuardrailResult:
    blocked: bool
    category: str | None
    matched_pattern: str | None


def check_input_guardrail(utterance: str) -> InputGuardrailResult:
    """KHONG dua vao safety_layer (chatbot-rag-design.md muc 7) - cau hoi y
    te hop le chua tu nhay cam (vd "uong qua lieu thi sao") PHAI di qua binh
    thuong, KHONG bi chan nham thanh injection (day la false-positive nguy
    hiem NHAT co the xay ra - chan nham 1 cau hoi cap cuu that)."""
    normalized = _normalize_for_pattern_match(utterance)
    for category, pattern in _COMPILED_INJECTION_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return InputGuardrailResult(blocked=True, category=category, matched_pattern=match.group(0))
    return InputGuardrailResult(blocked=False, category=None, matched_pattern=None)


# ---------------------------------------------------------------------------
# 12.2 Output guardrails
# ---------------------------------------------------------------------------

OUTPUT_GUARDRAIL_FALLBACK_MESSAGE = (
    "Xin lỗi, có lỗi khi xử lý câu trả lời. Vui lòng thử hỏi lại hoặc liên hệ bác sĩ."
)

# Regex cho cac dang secret DA TUNG dung trong repo (su co api.txt) + dinh
# dang pho bien - chan o TANG OUTPUT, khong phu thuoc viec secret co lot vao
# context hay khong (lop phong ve cuoi, khong phai lop chinh).
_SECRET_PATTERNS: list[tuple[str, str]] = [
    ("openai_api_key", r"sk-[A-Za-z0-9_-]{20,}"),
    ("postgres_connection_string", r"postgres(?:ql)?://[^\s]+:[^\s]+@[^\s]+"),
    ("generic_bearer_token", r"\bBearer\s+[A-Za-z0-9._-]{20,}\b"),
]
_COMPILED_SECRET_PATTERNS = [(name, re.compile(pattern)) for name, pattern in _SECRET_PATTERNS]

# UUID v4-dang chuan (8-4-4-4-12 hex) - dinh dang patient_id pho bien trong
# du lieu seed/test cua repo nay. Khong bat duoc patient_id KHONG phai dang
# UUID (vd slug tuy y nhu "demo-patient-01") - gioi han da biet, ghi ro o
# docstring check_output_guardrail.
_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


@dataclass
class OutputGuardrailResult:
    response: str
    redacted: bool
    redaction_reasons: list[str]


def check_output_guardrail(response: str, current_patient_id: str) -> OutputGuardrailResult:
    """Chay SAU answer_generation, TRUOC khi tra ve nguoi dung. 2 kiem tra
    doc lap, CA HAI co the trigger cung luc:
      1. Secret pattern (API key/connection string/token) - redact ngay,
         khong tra nguyen van ra ngoai.
      2. UUID KHAC current_patient_id xuat hien trong response - dau hieu
         ro ri du lieu bệnh nhan khac, thay response bang fallback AN TOAN
         (khong chi redact 1 phan, vi khong biet con thong tin nao khac cua
         benh nhan do bi lo trong cung cau tra loi).

    GIOI HAN DA BIET: kiem tra (2) chi bat duoc patient_id dang UUID chuan -
    KHONG bat duoc slug tuy y (vd "demo-patient-01") vi khong co dinh dang
    co dinh de nhan dien "day la 1 patient_id" ma khong biet truoc danh sach
    that. Day la lop phong ve BO SUNG (defense-in-depth), KHONG thay the
    viec moi tool da filter dung patient_id o tang SQL (Phase 5b).

    QUAN TRONG - `redaction_reasons` KHONG duoc chua gia tri THAT da bi lo
    (vd UUID cua benh nhan khac, doan secret) - chi ghi TEN LOAI phat hien
    duoc. Ly do: `reasons` nay se chay thang vao `trace`/`AuditLog` (luu
    Postgres, doc duoc boi bac si + doi ky thuat, chatbot-rag-design.md muc
    5.2/7) - neu embed thang gia tri ro ri vao day, chinh cai audit log dung
    de PHAT HIEN ro ri lai TRO THANH 1 noi luu ro ri thu 2, vinh vien trong
    DB thay vi chi thoang qua trong 1 response bi chan."""
    reasons: list[str] = []

    other_patient_uuid_found = any(
        m.group(0) != current_patient_id for m in _UUID_RE.finditer(response)
    )
    if other_patient_uuid_found:
        reasons.append("other_patient_id_detected")
        return OutputGuardrailResult(response=OUTPUT_GUARDRAIL_FALLBACK_MESSAGE, redacted=True, redaction_reasons=reasons)

    redacted_response = response
    for name, pattern in _COMPILED_SECRET_PATTERNS:
        if pattern.search(redacted_response):
            reasons.append(f"secret_pattern:{name}")
            redacted_response = pattern.sub("[ĐÃ ẨN]", redacted_response)

    return OutputGuardrailResult(
        response=redacted_response, redacted=bool(reasons), redaction_reasons=reasons
    )