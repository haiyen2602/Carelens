"""FEAT-007 — danh gia muc nghiem trong khi benh nhan Missed/Delayed/co
SideEffect an trong cau noi (chatbot-rag-design.md muc 8, business-rules.md
BR-3.1 - BR-3.6).

`combine_severity()` la PURE FUNCTION - khong DB/API - de test rieng duoc
INVARIANT quan trong nhat cua tinh nang nay: "chi nang, khong bao gio ha"
(BR-3.2 + BR-3.6). Day la loai bug am tham nguy hiem giong bug
word_similarity_threshold o Phase 4 - neu code sai chieu (vd lay trung binh
cong thay vi max, hoac de fallback ghi de thang RAG), khong co loi nao bao,
chi co 1 benh nhan bi ha muc nghiem trong 1 cach am tham it lau sau."""

from __future__ import annotations

SEVERITY_RANK: dict[str, int] = {"Nhẹ": 1, "Trung bình": 2, "Nguy hiểm": 3}
_RANK_TO_SEVERITY: dict[int, str] = {v: k for k, v in SEVERITY_RANK.items()}

# Phase 6: api-contracts.md (§4 chat-api, §6 escalation-api) dung quy uoc
# tieng Anh LOW|MEDIUM|HIGH cho severity trong moi DTO huong ra ngoai (FE,
# EscalationDTO) - KHAC voi ConversationState.severity noi bo (tieng Viet,
# chot o chatbot-rag-design.md muc 9). Chi 1 noi chuyen doi, dung o bien
# FastAPI/escalate_fn, khong de 2 quy uoc lan nhau trong logic nghiep vu.
SEVERITY_VI_TO_EN: dict[str, str] = {"Nhẹ": "LOW", "Trung bình": "MEDIUM", "Nguy hiểm": "HIGH"}


def combine_severity(rag_severity: str | None, fallback_severity: str) -> str:
    """Ket hop danh gia RAG per-thuoc (nguon chinh, tu tac_dung/tac_dung_phu
    - xem build_severity_node) voi `muc_nghiem_trong` (fallback/prior tinh
    san theo 52 tieu muc - BR-3.6) thanh 1 muc cuoi cung.

    Quy tac (BR-3.2 + BR-3.6, CHI NANG KHONG HA):
      - RAG khong ro rang (`rag_severity is None` - vd khong co chunk nao
        cho dung thuoc, hoac classify_fn tra ve khong chac chan) -> BR-3.2:
        an toan truoc, san la "Trung bình" (KHONG duoc suy dien xuong "Nhẹ"
        chi vi thieu du lieu).
      - RAG co ket qua ro rang -> do la muc SAN (floor). `fallback_severity`
        (muc_nghiem_trong) chi co the NANG muc san nay len cao hon, khong
        bao gio duoc phep KEO XUONG thap hon muc RAG da suy ra (BR-3.6:
        "chi nang len chu khong ha thap muc da suy ra tu RAG").

    Trien khai: MAX(rank(floor), rank(fallback)) - khong phai trung binh
    cong, khong phai uu tien nguon nao "tin cay hon" theo thu tu if/elif de
    dang cai sai chieu."""
    if fallback_severity not in SEVERITY_RANK:
        raise ValueError(f"fallback_severity khong hop le: {fallback_severity!r}")
    if rag_severity is not None and rag_severity not in SEVERITY_RANK:
        raise ValueError(f"rag_severity khong hop le: {rag_severity!r}")

    floor_rank = SEVERITY_RANK["Trung bình"] if rag_severity is None else SEVERITY_RANK[rag_severity]
    final_rank = max(floor_rank, SEVERITY_RANK[fallback_severity])
    return _RANK_TO_SEVERITY[final_rank]
