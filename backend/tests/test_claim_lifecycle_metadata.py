import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote
from uuid import uuid4

import pytest
from sqlalchemy import BigInteger, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.models.database import (
    Base,
    ClaimRecord,
    DATABASE_URL,
    _MIGRATION_COLUMNS,
    migrate_schema,
)


def test_claim_record_declares_server_owned_queue_and_lifecycle_metadata():
    columns = ClaimRecord.__table__.c

    received_at = columns.received_at
    assert received_at.type.timezone is True
    assert received_at.nullable is False
    assert received_at.server_default is not None
    assert "CURRENT_TIMESTAMP" in str(received_at.server_default.arg).upper()
    assert received_at.onupdate is None

    queue_sequence = columns.queue_sequence
    assert isinstance(queue_sequence.type, BigInteger)
    assert queue_sequence.nullable is False
    assert queue_sequence.server_default is not None
    assert "NEXT SEQUENCE VALUE" in str(queue_sequence.server_default.arg).upper()
    assert queue_sequence.onupdate is None

    assert columns.analysis_started_at.nullable is True
    assert columns.analysis_started_at.type.timezone is True
    assert columns.analysis_heartbeat_at.nullable is True
    assert columns.analysis_heartbeat_at.type.timezone is True
    assert columns.analyzed_at.nullable is True
    assert columns.analyzed_at.type.timezone is True
    assert columns.verified_at.nullable is True
    assert columns.verified_at.type.timezone is True

    analysis_attempts = columns.analysis_attempts
    assert analysis_attempts.nullable is False
    assert analysis_attempts.server_default is not None
    assert str(analysis_attempts.server_default.arg) == "0"

    assert columns.last_analysis_error.nullable is True
    assert columns.last_analysis_error_code.nullable is True
    assert columns.analysis_generation.nullable is True


def test_startup_migration_includes_all_claim_lifecycle_columns():
    migrated_columns = {
        column_definition.split()[0]
        for column_definition in _MIGRATION_COLUMNS["claims"]
    }

    assert migrated_columns == {
        "admission_date",
        "discharge_date",
        "medication_json",
        "referral_json",
        "received_at",
        "queue_sequence",
        "analysis_started_at",
        "analysis_heartbeat_at",
        "analyzed_at",
        "verified_at",
        "analysis_attempts",
        "last_analysis_error",
        "last_analysis_error_code",
        "analysis_generation",
    }


def _integration_claim(claim_id: str) -> ClaimRecord:
    return ClaimRecord(
        claim_id=claim_id,
        patient_id=f"PAT-{claim_id}",
        provider_id="FAC-INTEGRATION",
        doctor_id="DR-INTEGRATION",
        diagnosis_primary="I10",
        diagnosis_secondary="",
        procedure_codes="",
        severity_level=1,
        cost_claimed=100.0,
        length_of_stay=1,
        status="pending",
    )


def _database_identity(url_string: str):
    url = make_url(url_string)
    query = url.query

    configured_schema = query.get("schema") or query.get("search_path")
    options = query.get("options", "")
    if isinstance(options, tuple):
        options = options[0]
    if not configured_schema:
        match = re.search(
            r"(?:^|\s)-c\s*(?:search_path|schema)\s*=\s*([^\s]+)",
            unquote(options),
        )
        configured_schema = match.group(1) if match else None

    def normalize_identifier(value: str | None) -> str:
        value = (value or "").strip()
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        return value.lower()

    def normalize_host(value: str | None) -> str:
        host = normalize_identifier(value)
        return "<local>" if host in {"localhost", "127.0.0.1", "::1"} else host

    schema_parts = tuple(
        normalize_identifier(part)
        for part in (configured_schema or "public").split(",")
        if part.strip()
    )
    return (
        normalize_host(url.host),
        url.port or 5432,
        normalize_identifier(url.database),
        normalize_identifier(url.username),
        schema_parts or ("public",),
    )


def _database_target_identity(url_string: str):
    identity = _database_identity(url_string)
    return identity[0], identity[1], identity[2], identity[4]


def test_database_identity_normalizes_postgres_defaults_and_schema():
    base = "postgresql+asyncpg://POSTGRES@localhost/aegis_health"
    explicit_defaults = "postgresql+asyncpg://postgres@127.0.0.1:5432/aegis_health?schema=public"

    assert _database_identity(base) == _database_identity(explicit_defaults)
    assert _database_target_identity(base) == _database_target_identity(
        "postgresql+asyncpg://other_user@127.0.0.1:5432/aegis_health?schema=public"
    )
    assert _database_identity(base) != _database_identity(
        "postgresql+asyncpg://postgres@db.example:5432/other"
    )
    assert _database_identity(base) != _database_identity(
        "postgresql+asyncpg://postgres@db.example:5432/aegis_health?schema=test"
    )


async def _skip_if_database_is_not_disposable(test_engine):
    known_tables = set(Base.metadata.tables)
    async with test_engine.connect() as connection:
        result = await connection.execute(text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        ))
        public_tables = [row.table_name for row in result]
        for table_name in public_tables:
            quoted_table_name = table_name.replace('"', '""')
            row_count = await connection.scalar(text(
                f'SELECT COUNT(*) FROM "public"."{quoted_table_name}"'
            ))
            if row_count:
                pytest.skip(
                    f"dedicated database is not disposable: public table "
                    f"{table_name!r} contains {row_count} rows"
                )
            if table_name not in known_tables:
                pytest.skip(
                    f"dedicated database is not disposable: unexpected public "
                    f"table {table_name!r} exists"
                )


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


@pytest.mark.asyncio
async def test_postgres_migration_preserves_claim_lifecycle_metadata():
    if os.getenv("RUN_DB_INTEGRATION") != "1":
        pytest.skip("set RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests")
    test_database_url = os.getenv("QUEUE_METADATA_TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip(
            "set QUEUE_METADATA_TEST_DATABASE_URL to an isolated PostgreSQL database"
        )
    if not test_database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("QUEUE_METADATA_TEST_DATABASE_URL must use postgresql+asyncpg")

    test_identity = _database_identity(test_database_url)
    app_target = _database_target_identity(DATABASE_URL)
    if not test_identity[2].lower().startswith(("test_", "queue_test_")):
        pytest.skip("dedicated PostgreSQL database name must start with test_ or queue_test_")
    if _database_target_identity(test_database_url) == app_target:
        pytest.skip(
            "QUEUE_METADATA_TEST_DATABASE_URL targets the application database"
        )

    bootstrap_engine = create_async_engine(test_database_url, echo=False)
    test_engine = None
    TestSessionLocal = None
    schema_name = f"queue_test_{uuid4().hex}"
    schema_created = False

    test_prefix = f"__test_claim_lifecycle_{uuid4().hex}"
    claim_ids = [f"{test_prefix}_z", f"{test_prefix}_a"]
    fresh_claim_ids = [f"{test_prefix}_fresh_{index}" for index in range(3)]
    try:
        await _skip_if_database_is_not_disposable(bootstrap_engine)
        async with bootstrap_engine.begin() as connection:
            await connection.execute(text(
                f"CREATE SCHEMA {_quote_identifier(schema_name)}"
            ))
        schema_created = True

        test_engine = create_async_engine(
            test_database_url,
            connect_args={
                "server_settings": {
                    "search_path": _quote_identifier(schema_name),
                }
            },
            echo=False,
        )
        TestSessionLocal = async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with test_engine.connect() as connection:
            assert await connection.scalar(text("SELECT current_schema()")) == schema_name
        async with test_engine.begin() as connection:
            other_tables = [
                table
                for table in Base.metadata.sorted_tables
                if table.name != "claims"
            ]
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection, tables=other_tables
                )
            )
            await connection.execute(text(
                """
                CREATE TABLE claims (
                    claim_id VARCHAR PRIMARY KEY,
                    patient_id VARCHAR NOT NULL,
                    provider_id VARCHAR NOT NULL,
                    doctor_id VARCHAR NOT NULL,
                    diagnosis_primary VARCHAR NOT NULL,
                    diagnosis_secondary VARCHAR NOT NULL,
                    procedure_codes VARCHAR NOT NULL,
                    severity_level INTEGER NOT NULL,
                    cost_claimed DOUBLE PRECISION NOT NULL,
                    length_of_stay INTEGER NOT NULL,
                    cbg_group_claimed VARCHAR NULL,
                    admission_date VARCHAR NULL,
                    discharge_date VARCHAR NULL,
                    medication_json VARCHAR NULL,
                    referral_json VARCHAR NULL,
                    status VARCHAR NOT NULL,
                    risk_score DOUBLE PRECISION NULL,
                    priority_tier VARCHAR NULL,
                    human_decision VARCHAR NULL
                )
                """
            ))
            await connection.execute(text(
                "CREATE INDEX ix_claims_queue_sequence ON claims (status)"
            ))
            await connection.execute(text(
                """
                INSERT INTO claims (
                    claim_id,
                    patient_id,
                    provider_id,
                    doctor_id,
                    diagnosis_primary,
                    diagnosis_secondary,
                    procedure_codes,
                    severity_level,
                    cost_claimed,
                    length_of_stay,
                    status
                ) VALUES
                    (:first_claim_id, :first_patient_id, 'FAC-LEGACY', 'DR-LEGACY',
                     'I10', '', '', 1, 100.0, 1, 'pending'),
                    (:second_claim_id, :second_patient_id, 'FAC-LEGACY', 'DR-LEGACY',
                     'I10', '', '', 1, 100.0, 1, 'pending')
                """
            ), {
                "first_claim_id": claim_ids[0],
                "first_patient_id": f"PAT-{claim_ids[0]}",
                "second_claim_id": claim_ids[1],
                "second_patient_id": f"PAT-{claim_ids[1]}",
            })
            await connection.execute(text(
                "DROP SEQUENCE IF EXISTS claims_queue_sequence_seq"
            ))
        migration_window_start = datetime.now(timezone.utc)
        await migrate_schema(test_engine)
        migration_window_end = datetime.now(timezone.utc)

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(ClaimRecord)
                .where(ClaimRecord.claim_id.in_(claim_ids))
                .order_by(ClaimRecord.queue_sequence)
            )
            legacy_rows = result.scalars().all()

        assert len(legacy_rows) == 2
        assert [claim.claim_id for claim in legacy_rows] == sorted(claim_ids)
        assert legacy_rows[0].queue_sequence < legacy_rows[1].queue_sequence
        assert all(claim.analysis_attempts == 0 for claim in legacy_rows)
        assert all(claim.analysis_started_at is None for claim in legacy_rows)
        assert all(claim.analysis_heartbeat_at is None for claim in legacy_rows)
        assert all(claim.analyzed_at is None for claim in legacy_rows)
        assert all(claim.verified_at is None for claim in legacy_rows)
        assert all(claim.last_analysis_error is None for claim in legacy_rows)
        assert legacy_rows[0].received_at == legacy_rows[1].received_at
        assert migration_window_start <= legacy_rows[0].received_at <= migration_window_end
        assert {claim.queue_sequence for claim in legacy_rows} == {1, 2}
        legacy_max_sequence = max(claim.queue_sequence for claim in legacy_rows)

        async with TestSessionLocal() as db:
            persisted_attempts = await db.scalar(
                select(ClaimRecord).where(
                    ClaimRecord.claim_id == legacy_rows[0].claim_id
                )
            )
            persisted_attempts.analysis_attempts = 5
            await db.commit()
        legacy_rows[0].analysis_attempts = 5

        async with test_engine.begin() as connection:
            await connection.execute(text(
                "SELECT setval('claims_queue_sequence_seq', :sequence_value, TRUE)"
            ), {"sequence_value": legacy_max_sequence + 100})
        await migrate_schema(test_engine)
        async with test_engine.connect() as connection:
            sequence_value = await connection.scalar(text(
                "SELECT last_value FROM claims_queue_sequence_seq"
            ))
        assert sequence_value == legacy_max_sequence + 100

        async with test_engine.begin() as connection:
            await connection.execute(text(
                "SELECT setval('claims_queue_sequence_seq', :sequence_value, TRUE)"
            ), {"sequence_value": 1})
        await migrate_schema(test_engine)
        async with test_engine.connect() as connection:
            sequence_value = await connection.scalar(text(
                "SELECT last_value FROM claims_queue_sequence_seq"
            ))
        assert sequence_value == legacy_max_sequence

        before_second_migration = {
            claim.claim_id: (
                claim.received_at,
                claim.queue_sequence,
                claim.analysis_attempts,
            )
            for claim in legacy_rows
        }

        await migrate_schema(test_engine)

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(ClaimRecord).where(ClaimRecord.claim_id.in_(claim_ids))
            )
            preserved = {claim.claim_id: claim for claim in result.scalars()}

        assert set(preserved) == set(claim_ids)
        for claim_id, (received_at, queue_sequence, analysis_attempts) in before_second_migration.items():
            assert preserved[claim_id].received_at == received_at
            assert preserved[claim_id].queue_sequence == queue_sequence
            assert preserved[claim_id].analysis_attempts == analysis_attempts

        async with TestSessionLocal() as db:
            with pytest.raises(SQLAlchemyError):
                await db.execute(
                    update(ClaimRecord)
                    .where(ClaimRecord.claim_id == legacy_rows[0].claim_id)
                    .values(received_at=datetime.now(timezone.utc) + timedelta(days=1))
                )
                await db.commit()
            await db.rollback()

            with pytest.raises(SQLAlchemyError):
                await db.execute(
                    update(ClaimRecord)
                    .where(ClaimRecord.claim_id == legacy_rows[0].claim_id)
                    .values(queue_sequence=legacy_rows[0].queue_sequence + 10000)
                )
                await db.commit()
            await db.rollback()

        async with test_engine.begin() as connection:
            for column_name in ("received_at", "queue_sequence", "analysis_attempts"):
                await connection.execute(text(
                    f"ALTER TABLE claims ALTER COLUMN {column_name} DROP NOT NULL"
                ))
            await connection.execute(text(
                "DROP TRIGGER IF EXISTS claims_metadata_immutable ON claims"
            ))
            await connection.execute(text(
                """
                UPDATE claims
                SET received_at = NULL,
                    queue_sequence = CASE
                        WHEN claim_id = :preserved_claim_id
                        THEN CAST(:preserved_queue_sequence AS BIGINT)
                        ELSE NULL::BIGINT
                    END,
                    analysis_attempts = NULL
                WHERE claim_id IN (:preserved_claim_id, :null_claim_id)
                """
            ), {
                "preserved_claim_id": legacy_rows[0].claim_id,
                "null_claim_id": legacy_rows[1].claim_id,
                "preserved_queue_sequence": legacy_rows[0].queue_sequence,
            })

        mixed_window_start = datetime.now(timezone.utc)
        await migrate_schema(test_engine)
        mixed_window_end = datetime.now(timezone.utc)

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(ClaimRecord)
                .where(ClaimRecord.claim_id.in_(claim_ids))
                .order_by(ClaimRecord.queue_sequence)
            )
            backfilled = result.scalars().all()

        assert len(backfilled) == 2
        assert all(claim.received_at is not None for claim in backfilled)
        assert all(claim.analysis_attempts == 0 for claim in backfilled)
        assert all(claim.analysis_started_at is None for claim in backfilled)
        assert all(claim.analysis_heartbeat_at is None for claim in backfilled)
        assert all(claim.analyzed_at is None for claim in backfilled)
        assert all(claim.verified_at is None for claim in backfilled)
        assert all(claim.last_analysis_error is None for claim in backfilled)
        assert backfilled[0].claim_id == legacy_rows[0].claim_id
        assert backfilled[0].queue_sequence == legacy_rows[0].queue_sequence
        assert backfilled[0].queue_sequence < backfilled[1].queue_sequence
        assert backfilled[0].received_at == backfilled[1].received_at
        assert mixed_window_start <= backfilled[0].received_at <= mixed_window_end
        backfilled_max_sequence = max(claim.queue_sequence for claim in backfilled)

        async with test_engine.connect() as connection:
            constraint_result = await connection.execute(text(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'claims'
                  AND column_name IN (
                      'received_at', 'queue_sequence', 'analysis_attempts'
                  )
                """
            ))
            assert {
                row.column_name: row.is_nullable
                for row in constraint_result
            } == {
                "received_at": "NO",
                "queue_sequence": "NO",
                "analysis_attempts": "NO",
            }

            trigger_count = await connection.scalar(text(
                """
                SELECT COUNT(*)
                FROM pg_trigger
                WHERE tgname = 'claims_metadata_immutable'
                  AND NOT tgisinternal
                """
            ))
            assert trigger_count == 1

            index_count = await connection.scalar(text(
                """
                SELECT COUNT(*)
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = 'claims'
                  AND indexname = 'ix_claims_queue_sequence'
                """
            ))
            assert index_count == 1

            index_result = await connection.execute(text(
                """
                SELECT
                    am.amname AS access_method,
                    i.indisunique AS is_unique,
                    i.indisprimary AS is_primary,
                    i.indnatts AS column_count,
                    i.indnkeyatts AS key_column_count,
                    bool_and(i.indpred IS NULL) AS is_unfiltered,
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
                GROUP BY am.amname, i.indisunique, i.indisprimary,
                         i.indnatts, i.indnkeyatts
                """
            ))
            index_info = index_result.mappings().one()
            assert index_info["access_method"] == "btree"
            assert index_info["is_unique"] is False
            assert index_info["is_primary"] is False
            assert index_info["column_count"] == 1
            assert index_info["key_column_count"] == 1
            assert index_info["is_unfiltered"] is True
            assert index_info["columns"] == ["queue_sequence"]

        lifecycle_values = {
            "analysis_started_at": datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc),
            "analysis_heartbeat_at": datetime(2026, 9, 13, 10, 2, tzinfo=timezone.utc),
            "analyzed_at": datetime(2026, 9, 13, 10, 5, tzinfo=timezone.utc),
            "verified_at": datetime(2026, 9, 13, 10, 10, tzinfo=timezone.utc),
        }
        async with TestSessionLocal() as db:
            db.add_all([_integration_claim(claim_id) for claim_id in fresh_claim_ids])
            await db.commit()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(ClaimRecord)
                .where(ClaimRecord.claim_id.in_(fresh_claim_ids))
                .order_by(ClaimRecord.queue_sequence)
            )
            fresh_claims = result.scalars().all()
            fresh_claim = fresh_claims[0]
            fresh_claim.analysis_started_at = lifecycle_values["analysis_started_at"]
            fresh_claim.analysis_heartbeat_at = lifecycle_values["analysis_heartbeat_at"]
            fresh_claim.analyzed_at = lifecycle_values["analyzed_at"]
            fresh_claim.verified_at = lifecycle_values["verified_at"]
            await db.commit()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(ClaimRecord)
                .where(ClaimRecord.claim_id.in_(fresh_claim_ids))
                .order_by(ClaimRecord.queue_sequence)
            )
            fresh_claims = result.scalars().all()

        assert len(fresh_claims) == len(fresh_claim_ids)
        assert all(claim.received_at is not None for claim in fresh_claims)
        assert all(claim.analysis_attempts == 0 for claim in fresh_claims)
        assert all(
            earlier.queue_sequence < later.queue_sequence
            for earlier, later in zip(fresh_claims, fresh_claims[1:])
        )
        assert fresh_claims[0].queue_sequence > backfilled_max_sequence
        fresh_claim = fresh_claims[0]
        assert fresh_claim.analysis_started_at == lifecycle_values["analysis_started_at"]
        assert fresh_claim.analysis_heartbeat_at == lifecycle_values["analysis_heartbeat_at"]
        assert fresh_claim.analyzed_at == lifecycle_values["analyzed_at"]
        assert fresh_claim.verified_at == lifecycle_values["verified_at"]

        async with test_engine.begin() as connection:
            await connection.execute(text(
                "DROP INDEX IF EXISTS ix_claims_queue_sequence"
            ))
            await connection.execute(text(
                "ALTER TABLE claims ADD CONSTRAINT ix_claims_queue_sequence "
                "UNIQUE (human_decision)"
            ))
        with pytest.raises(RuntimeError, match="constraint"):
            await migrate_schema(test_engine)

        async with test_engine.begin() as connection:
            await connection.execute(text(
                "ALTER TABLE claims DROP CONSTRAINT ix_claims_queue_sequence"
            ))
        await migrate_schema(test_engine)
    finally:
        if test_engine is not None:
            await test_engine.dispose()
        if schema_created:
            async with bootstrap_engine.begin() as connection:
                await connection.execute(text(
                    f"DROP SCHEMA {_quote_identifier(schema_name)} CASCADE"
                ))
        await bootstrap_engine.dispose()
