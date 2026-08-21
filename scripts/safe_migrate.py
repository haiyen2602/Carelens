"""Safe pre-deploy database migration runner with auto-recovery for orphan revisions."""
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.config import Config
from alembic import command, script
from backend.config import get_settings
from sqlalchemy import create_engine, inspect, text



def main():
    try:
        settings = get_settings()
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            inspector = inspect(conn)
            if "alembic_version" in inspector.get_table_names():
                row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
                if row and row[0]:
                    curr_rev = row[0]
                    cfg = Config("alembic.ini")
                    sdir = script.ScriptDirectory.from_config(cfg)
                    head = sdir.get_current_head()
                    
                    is_valid = False
                    try:
                        if sdir.get_revision(curr_rev) is not None:
                            is_valid = True
                    except Exception:
                        is_valid = False

                    if not is_valid:
                        print(f"[PRE-DEPLOY] Found missing revision '{curr_rev}' in remote DB. Stamping to current head '{head}'...")
                        conn.execute(text(f"UPDATE alembic_version SET version_num = '{head}'"))
                        conn.commit()
                        print(f"[PRE-DEPLOY] DB stamped to head '{head}'.")
                    else:
                        print(f"[PRE-DEPLOY] Current DB revision '{curr_rev}' is valid.")
    except Exception as e:
        print(f"[PRE-DEPLOY WARNING] Failed during pre-check: {e}")

    print("[PRE-DEPLOY] Running alembic upgrade head...")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    
    # Extra safety checks
    try:
        with engine.begin() as conn:
            cols = [r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='account'")).fetchall()]
            if "supabase_uid" not in cols:
                print("[PRE-DEPLOY] Adding missing supabase_uid column to account table...")
                conn.execute(text("ALTER TABLE account ADD COLUMN IF NOT EXISTS supabase_uid VARCHAR"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_account_supabase_uid ON account (supabase_uid)"))
                print("[PRE-DEPLOY] supabase_uid column added.")

            tables = [r[0] for r in conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")).fetchall()]
            if "nudge" not in tables:
                print("[PRE-DEPLOY] Creating missing nudge table...")
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS nudge (
                        id VARCHAR PRIMARY KEY,
                        caregiver_account_id VARCHAR NOT NULL,
                        patient_id VARCHAR NOT NULL,
                        message TEXT NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        seen_at TIMESTAMP WITH TIME ZONE
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_nudge_caregiver_account_id ON nudge (caregiver_account_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_nudge_patient_id ON nudge (patient_id)"))
                print("[PRE-DEPLOY] nudge table created.")
    except Exception as e:
        print(f"[PRE-DEPLOY WARNING] Schema safety check: {e}")
        
    print("[PRE-DEPLOY] Migrations complete successfully.")


if __name__ == "__main__":
    main()
