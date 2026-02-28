"""create model_catalog table

Revision ID: 20260228_001
Revises: db00f3f1779d
Create Date: 2026-02-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260228_001'
down_revision: Union[str, None] = 'db00f3f1779d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建 model_catalog 表
    op.create_table(
        'model_catalog',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('model_id', sa.String(100), nullable=False, unique=True),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('provider_id', sa.String(32), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('input_price', sa.Numeric(10, 4), nullable=False, server_default='0'),
        sa.Column('output_price', sa.Numeric(10, 4), nullable=False, server_default='0'),
        sa.Column('cache_write_price', sa.Numeric(10, 4), server_default='0'),
        sa.Column('cache_read_price', sa.Numeric(10, 4), server_default='0'),
        sa.Column('context_window', sa.Integer(), nullable=True),
        sa.Column('max_output', sa.Integer(), nullable=True),
        sa.Column('supports_vision', sa.Boolean(), server_default='0'),
        sa.Column('supports_tools', sa.Boolean(), server_default='1'),
        sa.Column('supports_streaming', sa.Boolean(), server_default='1'),
        sa.Column('status', sa.String(20), server_default='pending'),  # pending, active, inactive
        sa.Column('is_pricing_confirmed', sa.Boolean(), server_default='0'),
        sa.Column('source', sa.String(20), server_default='manual'),  # auto_discovered, manual, builtin_default
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # 创建索引
    op.create_index('idx_model_catalog_provider', 'model_catalog', ['provider_id'])
    op.create_index('idx_model_catalog_status', 'model_catalog', ['status'])


def downgrade() -> None:
    op.drop_index('idx_model_catalog_status', 'model_catalog')
    op.drop_index('idx_model_catalog_provider', 'model_catalog')
    op.drop_table('model_catalog')
