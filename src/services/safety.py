"""Safety layer - keyword rules OR LLM, chay song song doc lap voi luong
chinh (ADR-0009, business-rules.md §6). File nay chi dinh nghia LOGIC phat
hien (keyword tat dinh + interface cho LLM layer) - viec "chay song song va
co the cat ngang giua chung" la trach nhiem cua orchestrator
(src/agents/orchestrator.py), khong phai cua module nay.

2 nhom redflag (BR-6.6):
  1. Trieu chung lam sang (kho tho, dau nguc...)
  2. Nguy co lieu dung bat thuong (BR-6.7/6.8, vd "toi co 10 vien thuoc ngu")
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

# Nhom 1 - trieu chung lam sang (business-rules.md §6, danh sach khoi tao).
CLINICAL_REDFLAG_KEYWORDS = [
    "kho tho",
    "dau nguc",
    "ngat",
    "xiu",
    "co giat",
    "non ra mau",
    "yeu liet nua nguoi",
    "noi kho",
    "meo mieng",
    "lu lan dot ngot",
    "chay mau khong cam",
    "sung mat",
    "sung moi",
    "noi me day toan than",
]

# Nhom 2 - nguy co lieu dung bat thuong (BR-6.7/6.8, bo sung 2026-08-04).
# Khong can khop dung ten thuoc trong phac do - an toan truoc, lam ro sau.
#
# THIET KE: dung 2 dieu kien DOC LAP (co so luong + co cum tu rui ro) thay vi
# 1 regex doi hoi dung THU TU tu ("uong X vien" vs "co X vien, uong...") -
# cau tieng Viet thuc te co ca 2 thu tu (vd "toi co 10 vien, uong het co sao
# khong" - so luong DUNG TRUOC dong tu "uong"). Regex thu tu cung nhac de bo
# sot bien the that (da bat duoc qua test that voi chinh cau vi du goc "toi
# co 10 vien thuoc ngu, uong het co sao khong" - xem tests/test_safety.py).
# Dung BR-6.2 (chap nhan bao thua, uu tien recall): AND long hon giua "co so
# luong+don vi" va "co cum tu rui ro" thay vi ep sat canh nhau.
_QUANTITY_RE = re.compile(r"\d+\s*(vien|lieu|goi|ong|vi|chai)\b")
_OVERDOSE_RISK_PHRASES = [
    "uong het",
    "uong gap doi",
    "uong gap ba",
    "uong gap 2",
    "uong gap 3",
    "uong ca",
    "uong mot luc",
    "co sao khong",
    "co lam sao khong",
    "duoc khong",
]


def _strip_diacritics(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _normalize(text: str) -> str:
    return _strip_diacritics(text or "").lower()


@dataclass
class SafetyFlag:
    is_redflag: bool
    matched_group: str | None  # "clinical" | "overdose_risk" | None
    matched_keyword: str | None
    source: str  # "keyword" | "llm" | "keyword+llm"


class LLMSafetyClassifier(Protocol):
    """Interface cho lop LLM cua safety layer - injectable de test khong can
    goi OpenAI that (BR-6.3: LLM loi/timeout thi keyword layer van phai chay
    doc lap, nen 2 lop nay KHONG duoc goi chung 1 ham/exception path)."""

    def __call__(self, utterance: str) -> bool: ...


def check_keyword_redflag(utterance: str) -> SafetyFlag:
    """Lop keyword - tat dinh, khong bao gio "chet" (khong goi API, khong
    exception phu thuoc mang). Day la luoi an toan luon song (ADR-0009)."""
    normalized = _normalize(utterance)

    for kw in CLINICAL_REDFLAG_KEYWORDS:
        if kw in normalized:
            return SafetyFlag(is_redflag=True, matched_group="clinical", matched_keyword=kw, source="keyword")

    quantity_match = _QUANTITY_RE.search(normalized)
    risk_phrase = next((p for p in _OVERDOSE_RISK_PHRASES if p in normalized), None)
    if quantity_match and risk_phrase:
        return SafetyFlag(
            is_redflag=True,
            matched_group="overdose_risk",
            matched_keyword=f"{quantity_match.group(0)!r} + {risk_phrase!r}",
            source="keyword",
        )

    return SafetyFlag(is_redflag=False, matched_group=None, matched_keyword=None, source="keyword")


def check_safety(utterance: str, llm_classifier: LLMSafetyClassifier | None = None) -> SafetyFlag:
    """OR logic (BR-6.1): 1 trong 2 lop co gia tri la du. Keyword luon chay
    truoc (khong phu thuoc gi) - neu da redflag thi khong can goi LLM (tiet
    kiem 1 lan goi). Neu keyword sach VA co llm_classifier, moi goi LLM;
    LLM loi (bat exception) khong duoc lam sap keyword layer da chay xong."""
    keyword_flag = check_keyword_redflag(utterance)
    if keyword_flag.is_redflag:
        return keyword_flag

    if llm_classifier is not None:
        try:
            llm_flagged = llm_classifier(utterance)
        except Exception:  # noqa: BLE001 - BR-6.3: loi LLM khong duoc lam mat ket qua keyword (da sach)
            llm_flagged = False
        if llm_flagged:
            return SafetyFlag(is_redflag=True, matched_group=None, matched_keyword=None, source="llm")

    return keyword_flag
