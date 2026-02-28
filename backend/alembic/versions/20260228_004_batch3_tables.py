"""Batch 3: model_usage_daily, model_pricing_history, user_model_limits

Revision ID: batch3_tables
Revises: 20260228_003_add_usage_fields_to_request_logs
Create Date: 2026-02-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'batch3_tables'
down_revision = '20260228_003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. model_usage_daily - 每日用量预聚合表
    op.create_table(
        'model_usage_daily',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('model_id', sa.String(100), nullable=False),
        sa.Column('key_id', UUID(as_uuid=True), sa.ForeignKey('user_api_keys.id', ondelete='SET NULL'), nullable=True),
        sa.Column('request_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('input_tokens', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('output_tokens', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('total_cost_usd', sa.Numeric(10, 4), server_default='0', nullable=False),
        sa.Column('avg_latency_ms', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_count', sa.Integer(), server_default='0', nullable=False),
        sa.UniqueConstraint('date', 'user_id', 'model_id', 'key_id', name='uq_model_usage_daily'),
    )
    op.create_index('idx_model_usage_daily_date', 'model_usage_daily', ['date'])
    op.create_index('idx_model_usage_daily_user', 'model_usage_daily', ['user_id', 'date'])
    op.create_index('idx_model_usage_daily_model', 'model_usage_daily', ['model_id', 'date'])

    # 2. model_pricing_history - 模型定价历史表
    op.create_table(
        'model_pricing_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('model_id', sa.String(100), nullable=False),
        sa.Column('old_input_price', sa.Numeric(10, 4), nullable=True),
        sa.Column('new_input_price', sa.Numeric(10, 4), nullable=False),
        sa.Column('old_output_price', sa.Numeric(10, 4), nullable=True),
        sa.Column('new_output_price', sa.Numeric(10, 4), nullable=False),
        sa.Column('changed_by', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=False),
        sa.Column('changed_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
    )
    op.create_index('idx_model_pricing_history_model', 'model_pricing_history', ['model_id'])
    op.create_index('idx_model_pricing_history_changed_at', 'model_pricing_history', ['changed_at'])

    # 3. user_model_limits - 用户模型级额度限制表
    op.create_table(
        'user_model_limits',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('model_id', sa.String(100), nullable=False),
        sa.Column('monthly_limit_usd', sa.Numeric(10, 2), nullable=True),
        sa.Column('daily_request_limit', sa.Integer(), nullable=True),
        sa.UniqueConstraint('user_id', 'model_id', name='uq_user_model_limits'),
    )
    op.create_index('idx_user_model_limits_user', 'user_model_limits', ['user_id'])
    op.create_index('idx_user_model_limits_model', 'user_model_limits', ['model_id'])


def downgrade() -> None:
    op.drop_index('idx_user_model_limits_model', 'user_model_limits')
    op.drop_index('idx_user_model_limits_user', 'user_model_limits')
    op.drop_table('user_model_limits')

    op.drop_index('idx_model_pricing_history_changed_at', 'model_pricing_history')
    op.drop_index('idx_model_pricing_history_model', 'model_pricing_history')
    op.drop_table('model_pricing_history')

    op.drop_index('idx_model_usage_daily_model', 'model_usage_daily')
    op.drop_index('idx_model_usage_daily_user', 'model_usage_daily')
    op.drop_index('idx_model_usage_daily_date', 'model_usage_daily')
    op.drop_table('model_usage_daily')
