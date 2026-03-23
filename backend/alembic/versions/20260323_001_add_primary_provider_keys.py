"""add primary_provider_keys to users

Revision ID: 20260323_001
Revises: 20260304_001
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260323_001'
down_revision: Union[str, None] = '20260304_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加 primary_provider_keys 字段到 users 表
    # 用于存储用户的供应商主 Key 绑定关系
    op.add_column('users', sa.Column('primary_provider_keys', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'primary_provider_keys')
