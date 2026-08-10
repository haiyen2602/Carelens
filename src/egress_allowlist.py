"""Egress allowlist (vong 2, chatbot-rag-design.md muc 12.4) - liet ke TUONG
MINH moi noi agent duoc phep goi RA NGOAI process. KHONG co tool-calling mo -
LLM khong tu chon duoc URL/endpoint de goi, moi cuoc goi ra ngoai deu qua 1
trong cac module/dich vu da khai o duoi day, co dinh trong code, khong phai
LLM tu quyet dinh goi gi.

Cap nhat file nay MOI KHI them 1 duong goi ra ngoai process moi - list nay la
nguon tham chieu duy nhat cho `tests/test_egress_allowlist.py` (test kien
truc scan import cua src/, xem file do)."""

from __future__ import annotations

# Module trong src/ duoc PHEP import truc tiep 1 HTTP client
# (requests/httpx/aiohttp/urllib.request) hoac tuong duong - MOI import nhu
# vay ngoai danh sach nay se bi test kien truc bat.
#
# Luu y: `langchain_openai`/`openai` SDK tu no dung httpx noi bo (dependency
# giao tiep OpenAI API that) - day la 1 dependency THAT DA VET (khong phai
# code tu viet goi tuy y), khong nam trong pham vi quet cua test (chi quet
# IMPORT TRUC TIEP httpx/requests/... trong code src/ cua repo nay, khong
# quet dependency cua dependency).
ALLOWED_EGRESS_MODULES: frozenset[str] = frozenset(
    {
        # OpenAI API that - classify/embed/generate (chatbot-rag-design.md muc 2)
        "src/services/embeddings.py",
        "src/services/llm.py",
    }
)

# Cac "kenh" logic (khong phai module Python cu the, ma la MUC DICH duoc
# phep) - ghi lai de nguoi doc sau hieu DUNG pham vi, khong chi doc duoc list
# module o tren ma khong biet TAI SAO:
#   1. OpenAI API (classify_intent/classify_dose/classify_severity/embed_query/
#      generate_answer) - qua src/services/embeddings.py, src/services/llm.py.
#   2. PostgreSQL - qua SQLAlchemy Session (khong phai "egress" ra Internet,
#      nhung la I/O ra process khac) - CHI qua cac ham tool co dinh da co
#      (src/agents/tools/*.py, src/services/retrieval.py) - KHONG co truy
#      van SQL dong tu input benh nhan o bat ky dau.
#   3. Escalate (gia dinh/bac si) - qua src/services/escalation.py, ham
#      escalate_fn co dinh (chua goi API ngoai that, hien la ghi DB - xem
#      docstring module do) - khi co tich hop that (SMS/push), THEM vao
#      ALLOWED_EGRESS_MODULES o tren.
#
# KHONG co: LLM tool-calling mo (function-calling voi URL/endpoint do LLM tu
# chon), KHONG co eval/ hay script nao trong pham vi quet (chi quet src/).