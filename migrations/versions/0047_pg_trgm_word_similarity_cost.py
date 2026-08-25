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
