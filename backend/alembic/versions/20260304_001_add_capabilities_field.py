"""add capabilities JSONB field to model_catalog

Revision ID: 20260304_001
Revises: 20260303_001
Create Date: 2026-03-04

为 model_catalog 表添加 capabilities JSONB 字段，
用于存储完整的模型能力结构（来自 models.dev）。

capabilities 结构示例：
{
    "temperature": true,
    "reasoning": false,
    "attachment": false,
    "toolcall": true,
    "interleaved": false,
    "input": {"text": true, "audio": false, "image": true, "video": false, "pdf": false},
    "output": {"text": true, "audio": false, "image": false, "video": false, "pdf": false}
}
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260304_001'
down_revision = '20260303_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加 capabilities JSONB 字段
    op.add_column('model_catalog', sa.Column('capabilities', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('model_catalog', 'capabilities')
