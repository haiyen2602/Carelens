"""Ad-hoc read-only data snapshot of the Railway Postgres. Temporary helper."""
import os
import sqlalchemy as sa

url = os.environ["DATABASE_PUBLIC_URL"]
if "sslmode" not in url:
    url += ("&" if "?" in url else "?") + "sslmode=require"
eng = sa.create_engine(url)


def show(title, sql):
    print(f"\n### {title}")
    with eng.connect() as c:
        try:
            res = c.execute(sa.text(sql))
        except Exception as e:  # noqa: BLE001
            print("  ERR", str(e).splitlines()[0][:140])
            return
        cols = list(res.keys())
        rows = res.all()
    if not rows:
        print("  (empty)")
        return
    print("  " + " | ".join(cols))
    for r in rows:
        print("  " + " | ".join("NULL" if v is None else str(v)[:60] for v in r))


show("account", "select id, email, role, status, full_name, email_verified_at is not null as verified, created_at from account order by id")
show("patient", "select * from patient limit 5")
show("caregiver_link cols", "select column_name, data_type from information_schema.columns where table_name='caregiver_link' order by ordinal_position")
show("prescription", "select id, patient_id, status, ten_thuoc, created_at from prescription order by id")
show("dose_event by status", "select status, count(*) from dose_event group by 1 order by 2 desc")
show("escalation by status", "select status, count(*) from escalation group by 1 order by 2 desc")
show("drug sample", "select id, ten_thuoc, hoat_chat, dang_bao_che from drug order by id limit 5")
show("drug_chunks sample", "select id, drug_name, length(content) as len, vector_dims(embedding) as dims from drug_chunks order by id limit 3")
show("chat_messages", "select role, count(*), max(created_at) as latest from chat_messages group by 1")
show("audit_log recent", "select action, count(*) as n, max(created_at) as latest from audit_log group by 1 order by n desc limit 10")
show("apscheduler_jobs", "select id, next_run_time from apscheduler_jobs")
show("pending_drug_confirmation", "select id, status, count(*) over () as total from pending_drug_confirmation limit 3")
show("patient extra cols (0017)", "select column_name from information_schema.columns where table_name='patient' order by ordinal_position")
