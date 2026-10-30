import json
import os
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import BigInteger, Column, String, Float, Integer, DateTime, Sequence, text
from dotenv import load_dotenv
from backend.app.core.versions import analysis_version_from_evidence

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:aegis_2026@localhost/aegis_health_db"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()
_claim_queue_sequence = Sequence("claims_queue_sequence_seq", metadata=Base.metadata)


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
    # Queue/lifecycle metadata. Receipt and queue order are database-owned values.
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    queue_sequence: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        server_default=_claim_queue_sequence.next_value(),
    )
    analysis_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analysis_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analysis_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_analysis_error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_analysis_error_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    analysis_generation: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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
    # Nullable keeps the migration safe; rows without this field are not current.
    analysis_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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
    analysis_generation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# Kolom yang ditambahkan setelah skema awal — migrasi ringan saat startup
# (create_all tidak menambah kolom baru ke tabel yang sudah ada).
_MIGRATION_COLUMNS: dict[str, list[str]] = {
    "claims": [
        "admission_date VARCHAR NULL",
        "discharge_date VARCHAR NULL",
        "medication_json VARCHAR NULL",
        "referral_json VARCHAR NULL",
        "received_at TIMESTAMP WITH TIME ZONE NULL",
        "queue_sequence BIGINT NULL",
        "analysis_started_at TIMESTAMP WITH TIME ZONE NULL",
        "analysis_heartbeat_at TIMESTAMP WITH TIME ZONE NULL",
        "analyzed_at TIMESTAMP WITH TIME ZONE NULL",
        "verified_at TIMESTAMP WITH TIME ZONE NULL",
        "analysis_attempts INTEGER NULL",
        "last_analysis_error VARCHAR NULL",
        "last_analysis_error_code VARCHAR NULL",
        "analysis_generation VARCHAR NULL",
    ],
    "risk_analyses": [
        "actual_cost FLOAT NULL",
        "predicted_cost_upper FLOAT NULL",
        "analysis_version INTEGER NULL",
    ],
    "human_decisions": [
        "analysis_generation VARCHAR NULL",
    ],
    "agent_runs": [
        "model_used VARCHAR NULL",
    ],
}


async def _backfill_analysis_versions(conn) -> None:
    """Stamp legacy rows only when their evidence contains valid JSON metadata."""
    rows = await conn.execute(text(
        "SELECT claim_id, evidence_json FROM risk_analyses "
        "WHERE analysis_version IS NULL"
    ))
    for claim_id, evidence_json in rows:
        version = analysis_version_from_evidence(evidence_json)
        if version is None:
            continue
        await conn.execute(
            text(
                "UPDATE risk_analyses SET analysis_version = :analysis_version "
                "WHERE claim_id = :claim_id AND analysis_version IS NULL"
            ),
            {"claim_id": claim_id, "analysis_version": version},
        )


async def migrate_schema(bind=None):
    """Tambahkan kolom yang hilang pada database yang sudah ada (idempotent)."""
    migration_engine = engine if bind is None else bind
    async with migration_engine.begin() as conn:
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

        await _backfill_analysis_versions(conn)
        await conn.execute(text(
            """
            CREATE OR REPLACE FUNCTION parse_jsonb_or_null(raw TEXT)
            RETURNS JSONB
            LANGUAGE plpgsql
            IMMUTABLE
            AS $function$
            BEGIN
                RETURN raw::jsonb;
            EXCEPTION WHEN others THEN
                RETURN NULL;
            END;
            $function$;
            """
        ))

        # Original receipt timestamps/order are unrecoverable. For preexisting rows,
        # received_at becomes migration time and queue_sequence follows deterministic
        # claim_id order only, before server-owned fields are required.
        await conn.execute(text(
            "CREATE SEQUENCE IF NOT EXISTS claims_queue_sequence_seq"
        ))
        await conn.execute(text(
            "UPDATE claims "
            "SET received_at = CURRENT_TIMESTAMP "
            "WHERE received_at IS NULL"
        ))
        await conn.execute(text(
            "UPDATE claims "
            "SET analysis_attempts = 0 "
            "WHERE analysis_attempts IS NULL"
        ))
        await conn.execute(text(
            """
            WITH numbered AS (
                SELECT
                    claim_id,
                    ROW_NUMBER() OVER (ORDER BY claim_id)
                    + COALESCE((
                        SELECT MAX(queue_sequence)
                        FROM claims
                        WHERE queue_sequence IS NOT NULL
                    ), 0) AS next_sequence
                FROM claims
                WHERE queue_sequence IS NULL
            )
            UPDATE claims AS c
            SET queue_sequence = numbered.next_sequence
            FROM numbered
            WHERE c.claim_id = numbered.claim_id
            """
        ))
        await conn.execute(text(
            """
            SELECT setval(
                'claims_queue_sequence_seq',
                GREATEST(
                    COALESCE((SELECT MAX(queue_sequence) FROM claims), 0),
                    (SELECT last_value FROM claims_queue_sequence_seq)
                ),
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM claims WHERE queue_sequence IS NOT NULL
                    ) THEN TRUE
                    ELSE (SELECT is_called FROM claims_queue_sequence_seq)
                END
            )
            """
        ))
        await conn.execute(text(
            "ALTER TABLE claims "
            "ALTER COLUMN received_at SET DEFAULT CURRENT_TIMESTAMP"
        ))
        await conn.execute(text(
            "ALTER TABLE claims "
            "ALTER COLUMN queue_sequence "
            "SET DEFAULT nextval('claims_queue_sequence_seq')"
        ))
        await conn.execute(text(
            "ALTER TABLE claims "
            "ALTER COLUMN analysis_attempts SET DEFAULT 0"
        ))
        await conn.execute(text(
            "ALTER TABLE claims ALTER COLUMN received_at SET NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE claims ALTER COLUMN queue_sequence SET NOT NULL"
        ))
        await conn.execute(text(
            "ALTER TABLE claims ALTER COLUMN analysis_attempts SET NOT NULL"
        ))
        # Repair ordinary malformed indexes; constraint-backed indexes are never
        # dropped automatically because their ownership must be resolved manually.
        index_result = await conn.execute(text(
            """
            SELECT
                i.indisunique AS is_unique,
                i.indisprimary AS is_primary,
                i.indnatts AS column_count,
                i.indnkeyatts AS key_column_count,
                am.amname AS access_method,
                bool_and(i.indpred IS NULL) AS is_unfiltered,
                bool_or(EXISTS (
                    SELECT 1
                    FROM pg_constraint AS constraint_record
                    WHERE constraint_record.conindid = i.indexrelid
                )) AS is_constraint_backed,
                array_agg(a.attname ORDER BY keys.ordinality) AS columns
            FROM pg_index AS i
            JOIN pg_class AS table_class ON table_class.oid = i.indrelid
            JOIN pg_namespace AS table_namespace
                ON table_namespace.oid = table_class.relnamespace
            JOIN pg_class AS index_class ON index_class.oid = i.indexrelid
            JOIN pg_am AS am ON am.oid = index_class.relam
            JOIN LATERAL unnest(i.indkey) WITH ORDINALITY
                AS keys(attnum, ordinality) ON TRUE
            LEFT JOIN pg_attribute AS a
                ON a.attrelid = i.indrelid AND a.attnum = keys.attnum
            WHERE table_namespace.nspname = current_schema()
              AND table_class.relname = 'claims'
              AND index_class.relname = 'ix_claims_queue_sequence'
            GROUP BY
                i.indisunique,
                i.indisprimary,
                i.indnatts,
                i.indnkeyatts,
                am.amname
            """
        ))
        queue_index = index_result.mappings().first()
        if queue_index is not None and not (
            queue_index["access_method"] == "btree"
            and not queue_index["is_unique"]
            and not queue_index["is_primary"]
            and queue_index["column_count"] == 1
            and queue_index["key_column_count"] == 1
            and queue_index["is_unfiltered"]
            and queue_index["columns"] == ["queue_sequence"]
        ):
            if queue_index["is_constraint_backed"]:
                raise RuntimeError(
                    "Cannot repair ix_claims_queue_sequence: it is backed by a "
                    "PostgreSQL constraint; remove or rename the constraint manually"
                )
            await conn.execute(text(
                "DROP INDEX IF EXISTS ix_claims_queue_sequence"
            ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_claims_queue_sequence "
            "ON claims (queue_sequence)"
        ))
        await conn.execute(text(
            """
            CREATE OR REPLACE FUNCTION prevent_claim_metadata_mutation()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $function$
            BEGIN
                IF NEW.received_at IS DISTINCT FROM OLD.received_at THEN
                    RAISE EXCEPTION 'claims.received_at is immutable';
                END IF;
                IF NEW.queue_sequence IS DISTINCT FROM OLD.queue_sequence THEN
                    RAISE EXCEPTION 'claims.queue_sequence is immutable';
                END IF;
                RETURN NEW;
            END;
            $function$;
            """
        ))
        await conn.execute(text(
            """
            DO $block$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_trigger
                    WHERE tgname = 'claims_metadata_immutable'
                      AND tgrelid = 'claims'::regclass
                      AND NOT tgisinternal
                ) THEN
                    CREATE TRIGGER claims_metadata_immutable
                    BEFORE UPDATE OF received_at, queue_sequence ON claims
                    FOR EACH ROW
                    EXECUTE FUNCTION prevent_claim_metadata_mutation();
                END IF;
            END;
            $block$;
            """
        ))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await migrate_schema()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
