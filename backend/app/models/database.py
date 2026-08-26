import os
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Column, String, Float, Integer, DateTime, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:jari_bpjs2026@localhost/jari_db"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClaimRecord(Base):
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    patient_id: Mapped[str] = mapped_column(String, index=True)
    provider_id: Mapped[str] = mapped_column(String, index=True)
    doctor_id: Mapped[str] = mapped_column(String)
    diagnosis_primary: Mapped[str] = mapped_column(String)
    diagnosis_secondary: Mapped[str] = mapped_column(String)
    procedure_codes: Mapped[str] = mapped_column(String)
    severity_level: Mapped[int] = mapped_column(Integer)
    cost_claimed: Mapped[float] = mapped_column(Float)
    length_of_stay: Mapped[int] = mapped_column(Integer)
    cbg_group_claimed: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Data klinis lengkap (sebelumnya hilang — audit finding #5.2)
    admission_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # ISO date string
    discharge_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # ISO date string
    medication_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON list[{name, quantity}]
    referral_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)    # JSON ReferralInfo
    # Status tracking
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | processed | verified
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    priority_tier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    human_decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)

class RiskAnalysisRecord(Base):
    __tablename__ = "risk_analyses"

    claim_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)

    # Detailed Scores
    clinical_score: Mapped[float] = mapped_column(Float, default=0.0)
    financial_score: Mapped[float] = mapped_column(Float, default=0.0)
    fraud_score: Mapped[float] = mapped_column(Float, default=0.0)
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Final Result
    total_score: Mapped[float] = mapped_column(Float)
    priority_tier: Mapped[str] = mapped_column(String)
    recommended_action: Mapped[str] = mapped_column(String)

    # Kolom untuk agregasi potensi penghematan via SQL (hindari full-scan JSON)
    actual_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_cost_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Storage
    evidence_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

class AgentRunRecord(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String, index=True)
    agent_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # 'success', 'error', 'timeout', 'fallback'
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    model_used: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    output_json: Mapped[str] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String, index=True)
    agent_name: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    details: Mapped[Optional[str]] = mapped_column(String, nullable=True)

class HumanDecisionRecord(Base):
    __tablename__ = "human_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String, index=True)
    decision: Mapped[str] = mapped_column(String)
    reviewer: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# Kolom yang ditambahkan setelah skema awal — migrasi ringan saat startup
# (create_all tidak menambah kolom baru ke tabel yang sudah ada).
_MIGRATION_COLUMNS: dict[str, list[str]] = {
    "claims": [
        "admission_date VARCHAR NULL",
        "discharge_date VARCHAR NULL",
        "medication_json VARCHAR NULL",
        "referral_json VARCHAR NULL",
    ],
    "risk_analyses": [
        "actual_cost FLOAT NULL",
        "predicted_cost_upper FLOAT NULL",
    ],
    "agent_runs": [
        "model_used VARCHAR NULL",
    ],
}


async def migrate_schema():
    """Tambahkan kolom yang hilang pada database yang sudah ada (idempotent)."""
    async with engine.begin() as conn:
        for table, columns in _MIGRATION_COLUMNS.items():
            for col_def in columns:
                col_name = col_def.split()[0]
                try:
                    await conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_def}"
                    ))
                except Exception as e:
                    # Kolom mungkin sudah ada di database lain yang tidak dukung IF NOT EXISTS
                    print(f"[migrate] Skip {table}.{col_name}: {e}")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await migrate_schema()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
