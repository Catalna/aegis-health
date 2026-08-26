import asyncio
import os
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://postgres:jari_bpjs2026@localhost/jari_db')
from backend.app.models.database import engine
from sqlalchemy import text

async def migrate():
    async with engine.begin() as conn:
        stmts = [
            "ALTER TABLE claims ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending'",
            "ALTER TABLE claims ADD COLUMN IF NOT EXISTS risk_score FLOAT",
            "ALTER TABLE claims ADD COLUMN IF NOT EXISTS priority_tier VARCHAR",
            "ALTER TABLE claims ADD COLUMN IF NOT EXISTS human_decision VARCHAR",
        ]
        for stmt in stmts:
            await conn.execute(text(stmt))
            print(f"OK: {stmt[:70]}")
    print("Migration complete!")

asyncio.run(migrate())
