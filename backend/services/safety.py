"""Safety layer - keyword rules OR LLM, chay song song doc lap voi luong
chinh (ADR-0009, business-rules.md §6). File nay chi dinh nghia LOGIC phat
hien (keyword tat dinh + interface cho LLM layer) - viec "chay song song va
co the cat ngang giua chung" la trach nhiem cua orchestrator
(src/agents/orchestrator.py), khong phai cua module nay.

2 nhom redflag CUA LOP KEYWORD (BR-6.6, khong doi tu truoc vong 3):
  1. Trieu chung lam sang (kho tho, dau nguc...)
  2. Nguy co lieu dung bat thuong (BR-6.7/6.8, vd "toi co 10 vien thuoc ngu")

VONG 3, MUC 3 (2026-08-12) - DOI KIEN TRUC, khong chi "them 1 lop":
dieu tra kien truc thuc te (chat-bot-build/vong-3-investigation.md, muc 2)
xac nhan production TRUOC DAY khong co lop LLM nao trong safety_layer ca -
`LLMSafetyClassifier` Protocol la 1 cho noi INJECTABLE nhung chua tung duoc
cam gia tri that (get_chat_services() wire default_safety_check(), goi
check_safety(utterance) KHONG kem llm_classifier). Day chinh la ly do cau
"toi muon uong 10 vien thuoc ngu" (khong co cum tu rui ro tuong minh nhu
"uong het") lot qua - khong phai 1 loi LLM bat truot, ma vi hoan toan khong
co duong nao khac ngoai regex de bat.

Tu vong 3: LLM la lop CHINH (chay LUON MOI LAN co llm_classifier, khong con
dieu kien "chi goi khi keyword sach" nhu thiet ke cu) - tra ve MUC DO
(khong con nhi phan, xem taxonomy 5 category o backend/services/
classification.py::classify_safety_llm), khong chi True/False - tranh rui ro
qua nhay khi mo rong nhan dien nhieu loai trieu chung hon (kickoff-prompt-
vong-3.md muc 3.2). Regex GIU LAM LOP PHONG VE PHU, chay SONG SONG that su
(khong phai fallback) - ket qua cuoi = MUC CAO HON giua 2 lop (regex chi co
dung 1 muc "Nguy hiểm" khi trigger, khong the bi LLM "ha muc").
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

# Thang muc do (vong 3) - dung ca cho keyword (chi co the la "Nguy hiểm" hoac
# "Không đáng ngại") lan LLM (du ca 4 muc). So sanh bang RANK, khong so sanh
# chuoi truc tiep.
_LEVEL_RANK = {"Không đáng ngại": 0, "Nhẹ": 1, "Trung bình": 2, "Nguy hiểm": 3}

# THEM 2026-08-12 (phan hoi review sau khi bao cao vong 3 - "chi nang khong
# ha" khi da co BANG CHUNG THUC NGHIEM ve dao dong, khong chi ly thuyet).
# eval/safety_llm_report.json (147 lan goi that, 20 lan/case bien) do duoc:
# self_harm_borderline dao dong Nhẹ/Trung bình 12/20 on dinh (60%),
# wrong_drug_borderline 10/20 (50%) - CA HAI deu KHONG BAO GIO tut ve "Không
# đáng ngại" (chi dao dong GIUA 2 muc deu co canh bao), nhung "may rui roi
# vao lan chay nao" van la rui ro that cho 2 category nay - ap "san" rieng:
# neu category la 1 trong 2 nay, khong bao gio de muc xuong duoi "Trung
# bình" cho DU 1 lan goi that su ra "Nhẹ"/"Không đáng ngại". Day la san
# THEO CATEGORY, khac voi "san" cua lop keyword (luon "Nguy hiểm") - 2 co
# che doc lap, khong thay the nhau.
_CATEGORY_LEVEL_FLOOR: dict[str, str] = {
    "self_harm": "Trung bình",
    "wrong_drug": "Trung bình",
}

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
    # True CHI KHI level == "Nguy hiểm" (cat ngang luong chinh - xem
    # orchestrator.py). "Trung bình"/"Nhẹ" KHONG cat luong (tranh bao dong
    # gia lien tuc, kickoff-prompt-vong-3.md muc 3.2) - van duoc ghi day du
    # vao trace de audit (level/llm_category/llm_reasoning).
    is_redflag: bool
    matched_group: str | None  # "clinical" | "overdose_risk" | None (LOP KEYWORD)
    matched_keyword: str | None
    source: str  # "keyword" | "llm" | "keyword+llm"
    level: str = "Nguy hiểm"  # MOI vong 3 - mac dinh "Nguy hiểm" giu dung y nghia CU cua keyword-only flag
    llm_category: str | None = None  # MOI - 1 trong 5 category taxonomy (muc 3.1), None neu LLM khong chay/khong flag
    llm_reasoning: str | None = None  # MOI - ly do ngan LLM dua ra, ghi vao trace de audit


class LLMSafetyResult(Protocol):
    """Cau truc ket qua LLM classifier tra ve - duck-typed (khong import
    truc tiep pydantic model tu classification.py de tranh phu thuoc vong)."""

    level: str  # "Không đáng ngại" | "Nhẹ" | "Trung bình" | "Nguy hiểm"
    category: str  # 1 trong 5 taxonomy (muc 3.1) hoac "none"
    reasoning: str


class LLMSafetyClassifier(Protocol):
    """Interface cho lop LLM cua safety layer - injectable de test khong can
    goi OpenAI that (BR-6.3: LLM loi/timeout thi keyword layer van phai chay
    doc lap, nen 2 lop nay KHONG duoc goi chung 1 ham/exception path).

    SUA vong 3: tra ve LLMSafetyResult (co muc do), khong con bool don thuan -
    xem docstring dau file."""

    def __call__(self, utterance: str) -> LLMSafetyResult: ...


def check_keyword_redflag(utterance: str) -> SafetyFlag:
    """Lop keyword - tat dinh, khong bao gio "chet" (khong goi API, khong
    exception phu thuoc mang). Day la luoi an toan luon song (ADR-0009)."""
    normalized = _normalize(utterance)

    for kw in CLINICAL_REDFLAG_KEYWORDS:
        if kw in normalized:
            return SafetyFlag(
                is_redflag=True, matched_group="clinical", matched_keyword=kw, source="keyword", level="Nguy hiểm"
            )

    quantity_match = _QUANTITY_RE.search(normalized)
    risk_phrase = next((p for p in _OVERDOSE_RISK_PHRASES if p in normalized), None)
    if quantity_match and risk_phrase:
        return SafetyFlag(
            is_redflag=True,
            matched_group="overdose_risk",
            matched_keyword=f"{quantity_match.group(0)!r} + {risk_phrase!r}",
            source="keyword",
            level="Nguy hiểm",
        )

    return SafetyFlag(
        is_redflag=False, matched_group=None, matched_keyword=None, source="keyword", level="Không đáng ngại"
    )


def check_safety(utterance: str, llm_classifier: LLMSafetyClassifier | None = None) -> SafetyFlag:
    """VONG 3 - LLM la lop CHINH, chay LUON MOI LAN co llm_classifier (khong
    con "chi goi khi keyword sach" nhu ban truoc vong 3 - xem docstring dau
    file). Ket qua cuoi = MUC CAO HON (theo _LEVEL_RANK) giua 2 lop - regex
    chi co 1 muc "Nguy hiểm" khi trigger nen luon la SAN, khong the bi LLM
    "ha muc". LLM loi (bat exception, vd timeout) KHONG duoc lam mat ket qua
    keyword da co (BR-6.3) - fallback ve keyword flag thuan, khong crash."""
    keyword_flag = check_keyword_redflag(utterance)

    if llm_classifier is None:
        return keyword_flag

    # Boc CA viec goi LAN doc ket qua trong 1 try/except - khong chi cuoc
    # goi (BR-6.3 ap dung cho MOI kieu that bai cua lop LLM, ke ca ket qua
    # sai dang du goi thanh cong, khong chi loi mang/timeout).
    try:
        llm_result = llm_classifier(utterance)
        llm_level = llm_result.level if llm_result.level in _LEVEL_RANK else "Không đáng ngại"
        llm_category = llm_result.category if llm_result.category and llm_result.category != "none" else None
        llm_reasoning = llm_result.reasoning
    except Exception:  # noqa: BLE001 - BR-6.3: loi LLM khong duoc lam mat ket qua keyword
        return keyword_flag

    # San theo category (xem _CATEGORY_LEVEL_FLOOR) - ap dung TRUOC buoc so
    # sanh voi keyword, de san nay cung duoc tinh vao "muc cao hon" nhu binh
    # thuong, khong phai 1 nhanh rieng de quen cap nhat sau nay.
    floor = _CATEGORY_LEVEL_FLOOR.get(llm_category)
    if floor and _LEVEL_RANK[floor] > _LEVEL_RANK[llm_level]:
        llm_level = floor

    if _LEVEL_RANK[llm_level] > _LEVEL_RANK[keyword_flag.level]:
        winning_level = llm_level
        source = "llm" if keyword_flag.level == "Không đáng ngại" else "keyword+llm"
    else:
        winning_level = keyword_flag.level
        source = keyword_flag.source if llm_level == "Không đáng ngại" else "keyword+llm"

    return SafetyFlag(
        is_redflag=winning_level == "Nguy hiểm",
        matched_group=keyword_flag.matched_group,
        matched_keyword=keyword_flag.matched_keyword,
        source=source,
        level=winning_level,
        llm_category=llm_category,
        llm_reasoning=llm_reasoning,
    )
