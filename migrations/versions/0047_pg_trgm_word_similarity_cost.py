"""BUILD-38: correct pg_trgm word_similarity/similarity operator COST.

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-25

BOI CANH (xem chat-bot-build/build_cai_thien/BUILD-38-QUALITY-IMPROVEMENT-LOOP-REPORT.md
muc Root Cause Analysis / Cluster A): moi RAG retrieval query that tren
production cho ``GENERAL_MEDICAL_INFORMATION`` mat 6-12 GIAY (do trung tren
tat ca 10/10 real retrieval span do duoc). Root-caused qua EXPLAIN ANALYZE
truc tiep: ``backend/services/retrieval.py::lexical_search``'s truy van
``noi_dung_unaccent <% :query`` (toan tu word_similarity, dung de tim doan
van ban tuong tu trong noi_dung dai) LUON bi query planner bo qua GIN
trigram index that co (``ix_drug_chunks_noi_dung_unaccent_trgm``), chon
``ix_drug_chunks_corpus_version`` (mot btree KHONG lien quan gi den trigram
matching) roi ap dung ``word_similarity()`` nhu mot filter tren TUNG dong
(~14000+ dong) - cham hon GIN index scan hang tram lan.

Nguyen nhan goc: catalog function ``word_similarity_op``/``similarity_op``
(function that dung boi toan tu ``<%``/``%``, KHAC voi ham cung ten
``word_similarity()``/``similarity()`` nguoi dung hay goi truc tiep) mac
dinh co ``COST = 1`` -- gia nhu ham nay re nhu phep cong so nguyen, trong
khi chi phi that (tinh trigram tren van ban dai) cao hon rat nhieu. Planner
vi vay danh gia sai plan nao re hon.

Fix da verify THAT (khong doan) tren ca local Postgres lan production (qua
tcp-proxy, read-only EXPLAIN ANALYZE): nang COST cua 2 ham nay len 100 khien
planner tu dong chon dung ``BitmapAnd`` giua ``ix_drug_chunks_corpus_version``
va ``ix_drug_chunks_noi_dung_unaccent_trgm`` -- giam thoi gian truy van tu
~8.6-12s xuong con ~3.1s (giam 65-75%). Phan con lai la chi phi that cua
GIN "recheck" (pg_trgm GIN la lossy index, luon can recheck) tren so dong
candidate that con lai - khong the giam them ma khong doi threshold/nguong
(mot thay doi ket qua tim kiem that su, ngoai pham vi build nay).

KHONG doi ket qua truy van (chi la cost hint cho planner, khong doi logic/
du lieu/thu tu operator) -- rui ro thap nhat trong cac phuong an da thu
nghiem (partial index moi, restructure query bang UNION/CTE deu KHONG hieu
qua hon, xem report). Idempotent (ALTER FUNCTION ... COST ghi de, khong
loi neu chay lai). Reversible that su (downgrade dat lai COST = 1, gia tri
mac dinh cua pg_trgm 1.6).

LUU Y: day la thuoc tinh cua pg_trgm EXTENSION function -- neu extension
duoc ALTER EXTENSION ... UPDATE trong tuong lai, COST co the bi reset ve
mac dinh cua extension; migration nay se can chay lai (idempotent, an
toan chay nhieu lan).

PR REVIEW RESPONSE (round 1): mot reviewer tu dong hoi dung -- day la
``ALTER FUNCTION`` toan CSDL (global), khong scope theo 1 truy van/session,
nen co the anh huong CA CAC truy van trigram KHAC ngoai
``backend/services/retrieval.py``. Da audit toan bo repo
(tim toan tu <%/%>/goi ham similarity trong backend/ va scripts/) va tim
dung 1 noi khac dung toan tu nay that:
``backend/services/drug_knowledge/resolver.py`` (tra cuu
ten thuoc theo bang ``drug``, ~3562 dong -- ho tro autocomplete cho bac
si). Da verify THAT (khong doan) bang cach dung du lieu that (copy tu
``drug_product.display_name`` vao bang scratch cung shape/index), chay
EXPLAIN ANALYZE voi COST=1 (truoc fix) va COST=100 (sau fix) cho dung truy
van resolver.py dung: **KE HOACH THUC THI GIONG HET CA 2 LAN** (``Seq Scan``
ca 2 truong hop, khong doi sang GIN index) -- vi bang ``drug`` nho (~3562
dong) va KHONG co index nao khac (nhu ``ix_drug_chunks_corpus_version``
cua ``drug_chunks``) tao ra "plan re gia" de planner nham lan chon sai --
day chinh la dieu kien CAN de bug goc (Cluster A) xay ra, va bang ``drug``
khong co dieu kien do. Ket luan: fix nay AN TOAN cho resolver.py, khong
regress.
"""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

_TARGET_COST = 100


def upgrade() -> None:
    op.execute(f"ALTER FUNCTION word_similarity_op(text, text) COST {_TARGET_COST}")
    op.execute(f"ALTER FUNCTION similarity_op(text, text) COST {_TARGET_COST}")


def downgrade() -> None:
    # 1 la gia tri mac dinh pg_trgm 1.6 tu dat cho moi function trong
    # extension (xem pg_proc.procost truoc khi migration nay tung chay).
    op.execute("ALTER FUNCTION word_similarity_op(text, text) COST 1")
    op.execute("ALTER FUNCTION similarity_op(text, text) COST 1")
