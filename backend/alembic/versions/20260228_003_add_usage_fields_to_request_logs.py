"""add usage fields to request_logs

Revision ID: 20260228_003
Revises: 20260228_002
Create Date: 2026-02-28

Note: request_logs already has cost_usd, latency_ms, prompt_tokens, completion_tokens
This migration adds:
- input_tokens (alias for prompt_tokens for consistency)
- output_tokens (alias for completion_tokens for consistency)
- cache_read_tokens
- cache_write_tokens
- key_plan

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260228_003'
down_revision: Union[str, None] = '20260228_002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加使用量相关字段到 request_logs 表
    # input_tokens 和 output_tokens 作为 prompt_tokens/completion_tokens 的别名
    op.add_column('request_logs', sa.Column('input_tokens', sa.Integer(), server_default='0'))
    op.add_column('request_logs', sa.Column('output_tokens', sa.Integer(), server_default='0'))
    op.add_column('request_logs', sa.Column('cache_read_tokens', sa.Integer(), server_default='0'))
    op.add_column('request_logs', sa.Column('cache_write_tokens', sa.Integer(), server_default='0'))
    op.add_column('request_logs', sa.Column('key_plan', sa.String(20), server_default='standard'))


def downgrade() -> None:
    op.drop_column('request_logs', 'key_plan')
    op.drop_column('request_logs', 'cache_write_tokens')
    op.drop_column('request_logs', 'cache_read_tokens')
    op.drop_column('request_logs', 'output_tokens')
    op.drop_column('request_logs', 'input_tokens')
