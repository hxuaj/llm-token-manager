"""add key_plan to provider_api_keys

Revision ID: 20260228_002
Revises: 20260228_001
Create Date: 2026-02-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260228_002'
down_revision: Union[str, None] = '20260228_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加 key_plan 相关字段到 provider_api_keys 表
    op.add_column('provider_api_keys', sa.Column('key_plan', sa.String(20), server_default='standard'))
    op.add_column('provider_api_keys', sa.Column('plan_models', sa.Text(), nullable=True))  # JSON 字符串
    op.add_column('provider_api_keys', sa.Column('plan_description', sa.Text(), nullable=True))
    op.add_column('provider_api_keys', sa.Column('override_input_price', sa.Numeric(10, 4), nullable=True))
    op.add_column('provider_api_keys', sa.Column('override_output_price', sa.Numeric(10, 4), nullable=True))


def downgrade() -> None:
    op.drop_column('provider_api_keys', 'override_output_price')
    op.drop_column('provider_api_keys', 'override_input_price')
    op.drop_column('provider_api_keys', 'plan_description')
    op.drop_column('provider_api_keys', 'plan_models')
    op.drop_column('provider_api_keys', 'key_plan')
