"""Reset the demo database + vector store (companion of scripts/demo_seed.py).

TRUNCATES all claim-related tables and wipes the local LanceDB folder so the next
server start re-backfills an empty vector table. Use ONLY on demonstrator data.

Usage:
    python scripts/demo_reset.py            # reads DATABASE_URL from .env
    python scripts/demo_reset.py --yes

After reset: restart the backend (the queue worker / LanceDB table are in-memory),
then run scripts/demo_seed.py.
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LANCEDB_DIR = REPO / "backend" / "app" / "lancedb_data"
TABLES = ("audit_logs", "human_decisions", "agent_runs", "risk_analyses", "claims")


def _database_dsn() -> str:
    url = None
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip()
            break
    if not url:
        raise SystemExit("DATABASE_URL not found in .env")
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def main(yes: bool) -> int:
    if not yes:
        answer = input("This TRUNCATES demo tables and wipes the LanceDB folder. Continue? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("aborted")
            return 1
    try:
        import asyncpg
    except ImportError:
        raise SystemExit("asyncpg not installed in this venv")

    dsn = _database_dsn()
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            for table in TABLES:
                try:
                    await conn.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
                    print(f"truncated {table}")
                except Exception as exc:  # table may not exist yet
                    print(f"skip {table}: {exc}")
            try:
                await conn.execute('DROP SEQUENCE IF EXISTS claims_queue_sequence_seq CASCADE')
            except Exception:
                pass
    finally:
        await conn.close()
    if LANCEDB_DIR.exists():
        shutil.rmtree(LANCEDB_DIR)
        print(f"wiped {LANCEDB_DIR}")
    else:
        print("no lancedb dir found; nothing wiped")
    print("reset done. RESTART the backend now, then run scripts/demo_seed.py.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", action="store_true", help="skip confirmation")
    sys.exit(asyncio.run(main(ap.parse_args().yes)))
