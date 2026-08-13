"""Ad-hoc read-only inspection of the Railway Postgres. Temporary helper."""
import os
import sqlalchemy as sa

url = os.environ["DATABASE_PUBLIC_URL"]
if "sslmode" not in url:
    url += ("&" if "?" in url else "?") + "sslmode=require"

eng = sa.create_engine(url, pool_pre_ping=True)
with eng.connect() as c:
    print("server:", c.execute(sa.text("select version()")).scalar_one().split(",")[0])
    print("db:", c.execute(sa.text("select current_database()")).scalar_one(),
          "| user:", c.execute(sa.text("select current_user")).scalar_one())
    print("size:", c.execute(sa.text(
        "select pg_size_pretty(pg_database_size(current_database()))")).scalar_one())
    exts = c.execute(sa.text(
        "select extname||' '||extversion from pg_extension order by 1")).scalars().all()
    print("extensions:", ", ".join(exts))
    try:
        print("alembic_version:", c.execute(
            sa.text("select version_num from alembic_version")).scalars().all())
    except Exception as e:  # noqa: BLE001
        print("alembic_version: MISSING", type(e).__name__)

    rows = c.execute(sa.text("""
        select c.relname,
               coalesce(s.n_live_tup, 0) as est,
               pg_size_pretty(pg_total_relation_size(c.oid)) as sz
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        left join pg_stat_user_tables s on s.relid = c.oid
        where n.nspname = 'public' and c.relkind = 'r'
        order by c.relname
    """)).all()

    print(f"\n{len(rows)} tables in public:\n")
    print(f"{'table':<34}{'rows':>10}  {'size':>10}")
    print("-" * 58)
    total = 0
    for name, est, sz in rows:
        exact = c.execute(sa.text(f'select count(*) from public."{name}"')).scalar_one()
        total += exact
        print(f"{name:<34}{exact:>10}  {sz:>10}")
    print("-" * 58)
    print(f"{'TOTAL':<34}{total:>10}")
