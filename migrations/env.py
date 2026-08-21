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


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Check for orphan/missing alembic revisions in remote DB (e.g. from deleted branches/hotfixes)
        try:
            from sqlalchemy import inspect as sa_inspect, text
            inspector = sa_inspect(connection)
            if "alembic_version" in inspector.get_table_names():
                row = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
                if row:
                    curr_rev = row[0]
                    script_dir = context.script
                    is_valid = False
                    try:
                        if curr_rev and script_dir.get_revision(curr_rev) is not None:
                            is_valid = True
                    except Exception:
                        is_valid = False

                    # If revision in DB is not known in current codebase revisions, auto-stamp to latest head
                    if not is_valid:
                        head_rev = script_dir.get_current_head()
                        print(f"[ALEMBIC AUTO-HEAL] Revision '{curr_rev}' in DB not found in repo. Auto-stamping to head '{head_rev}'...")
                        connection.execute(text(f"UPDATE alembic_version SET version_num = '{head_rev}'"))
                        connection.commit()
        except Exception as heal_err:
            print(f"[ALEMBIC WARNING] Auto-heal check warning: {heal_err}")

        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()



if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
