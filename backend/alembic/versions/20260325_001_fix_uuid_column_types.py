"""fix UUID column types from VARCHAR(32) to native UUID

Fixes the "value too long for type character varying(32)" error caused by
inserting 36-char UUID strings into VARCHAR(32) columns on PostgreSQL.

Root cause: migration files were previously using String(32) for UUID columns.
They have been corrected to String(36), but databases created before the fix
still have VARCHAR(32) columns. This migration converts them to native UUID
type, matching the GUID() model type used by all models.

Only applies to PostgreSQL. SQLite uses CHAR(32) by design (GUID type stores
32-char hex strings without hyphens on non-PostgreSQL databases).

Revision ID: 20260325_001
Revises: 20260324_001
Create Date: 2026-03-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260325_001'
down_revision: Union[str, None] = '20260324_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Foreign key relationships: (table, column, ref_table, ref_column, ondelete)
FK_RELATIONSHIPS = [
    ('provider_api_keys', 'provider_id', 'providers', 'id', 'CASCADE'),
    ('user_api_keys', 'user_id', 'users', 'id', 'CASCADE'),
    ('request_logs', 'user_id', 'users', 'id', 'SET NULL'),
    ('request_logs', 'key_id', 'user_api_keys', 'id', 'SET NULL'),
    ('request_logs', 'provider_id', 'providers', 'id', 'SET NULL'),
    ('monthly_usage', 'user_id', 'users', 'id', 'CASCADE'),
    ('model_pricing', 'provider_id', 'providers', 'id', 'CASCADE'),
    ('model_catalog', 'provider_id', 'providers', 'id', 'CASCADE'),
    ('model_usage_daily', 'user_id', 'users', 'id', 'CASCADE'),
    ('model_usage_daily', 'key_id', 'user_api_keys', 'id', 'SET NULL'),
    ('model_pricing_history', 'changed_by', 'users', 'id', 'SET NULL'),
    ('user_model_limits', 'user_id', 'users', 'id', 'CASCADE'),
]

# All UUID columns (primary keys + foreign keys) across all tables
UUID_COLUMNS = [
    ('users', 'id'),
    ('providers', 'id'),
    ('provider_api_keys', 'id'),
    ('provider_api_keys', 'provider_id'),
    ('user_api_keys', 'id'),
    ('user_api_keys', 'user_id'),
    ('request_logs', 'id'),
    ('request_logs', 'user_id'),
    ('request_logs', 'key_id'),
    ('request_logs', 'provider_id'),
    ('monthly_usage', 'id'),
    ('monthly_usage', 'user_id'),
    ('model_pricing', 'id'),
    ('model_pricing', 'provider_id'),
    ('model_catalog', 'id'),
    ('model_catalog', 'provider_id'),
    ('model_usage_daily', 'id'),
    ('model_usage_daily', 'user_id'),
    ('model_usage_daily', 'key_id'),
    ('model_pricing_history', 'id'),
    ('model_pricing_history', 'changed_by'),
    ('user_model_limits', 'id'),
    ('user_model_limits', 'user_id'),
]


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    # Step 1: Drop all FK constraints (IF EXISTS for idempotency)
    for table, column, *_ in FK_RELATIONSHIPS:
        constraint_name = f"{table}_{column}_fkey"
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint_name}"
        )

    # Step 2: Convert VARCHAR(32/36) columns to native UUID
    for table, column in UUID_COLUMNS:
        op.execute(f"""
            DO $$
            BEGIN
                ALTER TABLE {table} ALTER COLUMN {column} TYPE UUID
                    USING {column}::UUID;
            EXCEPTION WHEN OTHERS THEN NULL;
            END $$;
        """)

    # Step 3: Re-create FK constraints with correct ondelete behavior
    for table, column, ref_table, ref_column, ondelete in FK_RELATIONSHIPS:
        constraint_name = f"{table}_{column}_fkey"
        op.execute(f"""
            DO $$
            BEGIN
                ALTER TABLE {table}
                    ADD CONSTRAINT {constraint_name}
                    FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_column})
                    ON DELETE {ondelete};
            EXCEPTION WHEN OTHERS THEN NULL;
            END $$;
        """)


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    # Step 1: Drop all FK constraints
    for table, column, *_ in FK_RELATIONSHIPS:
        constraint_name = f"{table}_{column}_fkey"
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint_name}"
        )

    # Step 2: Convert UUID back to VARCHAR(32)
    for table, column in UUID_COLUMNS:
        op.execute(f"""
            DO $$
            BEGIN
                ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR(32)
                    USING {column}::VARCHAR(32);
            EXCEPTION WHEN OTHERS THEN NULL;
            END $$;
        """)

    # Step 3: Re-create FK constraints
    for table, column, ref_table, ref_column, ondelete in FK_RELATIONSHIPS:
        constraint_name = f"{table}_{column}_fkey"
        op.execute(f"""
            DO $$
            BEGIN
                ALTER TABLE {table}
                    ADD CONSTRAINT {constraint_name}
                    FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_column})
                    ON DELETE {ondelete};
            EXCEPTION WHEN OTHERS THEN NULL;
            END $$;
        """)
