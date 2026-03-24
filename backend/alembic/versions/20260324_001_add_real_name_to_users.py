"""add real_name to users

Revision ID: 20260324_001
Revises: 20260323_001
Create Date: 2026-03-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260324_001'
down_revision: Union[str, None] = '20260323_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加 real_name 字段到 users 表
    # 用于存储用户的真实姓名
    op.add_column('users', sa.Column('real_name', sa.String(100), nullable=True))

    # 为已有用户设置默认值
    op.execute("UPDATE users SET real_name = username WHERE real_name IS NULL")

    # 设置为 NOT NULL
    op.alter_column('users', 'real_name', nullable=False)


def downgrade() -> None:
    op.drop_column('users', 'real_name')
