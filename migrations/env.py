from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.config import get_settings
from backend.db.base import Base
from backend.db.models import AuditLog, DrugChunk  # noqa: F401 - import de dang ky vao Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Lay DATABASE_URL tu settings (.env) thay vi hardcode trong alembic.ini,
# de tranh lech giua migration va app luc chay that.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _check_known_revision(connectable) -> None:
    """Chan deploy neu alembic_version tro toi mot revision khong co trong repo.

    Dung connection rieng, tach khoi connection alembic se dung de chay
    migration - doc qua inspector/SELECT tren cung connection se mo mot
    transaction ngam khien alembic khong con lam chu duoc transaction va
    khong ai commit (xem docs/bug-report-alembic-env-silent-migration.md).
    """
    from sqlalchemy import inspect as sa_inspect, text

    with connectable.connect() as check_conn:
        inspector = sa_inspect(check_conn)
        if "alembic_version" not in inspector.get_table_names():
            return
        row = check_conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
        if not row:
            return
        curr_rev = row[0]
        script_dir = context.script
        try:
            is_valid = curr_rev and script_dir.get_revision(curr_rev) is not None
        except Exception:
            is_valid = False
        if not is_valid:
            raise RuntimeError(
                f"[ALEMBIC] Revision '{curr_rev}' trong alembic_version khong ton tai trong "
                "repo hien tai (co the do branch/hotfix da xoa). Tu dong stamp len head da "
                "bi bo vi che gia thanh cong: no danh dau moi migration da chay du thuc te "
                "chua chay cai nao. Kiem tra tay revision nay va chay "
                "'alembic stamp <revision_dung>' hoac 'alembic upgrade head' truoc khi deploy lai."
            )


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    _check_known_revision(connectable)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()



if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
