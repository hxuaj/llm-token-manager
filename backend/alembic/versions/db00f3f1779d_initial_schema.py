"""initial_schema

Revision ID: db00f3f1779d
Revises:
Create Date: 2026-02-28 12:32:15.572913

创建所有基础表：users, providers, provider_api_keys, user_api_keys,
request_logs, monthly_usage, model_pricing
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db00f3f1779d'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== users 表 ==========
    op.create_table(
        'users',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('username', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('email', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), server_default='user', nullable=False),
        sa.Column('monthly_quota_usd', sa.Numeric(10, 2), server_default='10.00', nullable=False),
        sa.Column('rpm_limit', sa.Integer(), server_default='30', nullable=False),
        sa.Column('allowed_models', sa.Text(), nullable=True),
        sa.Column('max_keys', sa.Integer(), server_default='5', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )

    # ========== providers 表 ==========
    op.create_table(
        'providers',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('base_url', sa.String(255), nullable=False),
        sa.Column('api_format', sa.String(20), server_default='openai', nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('config', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )

    # ========== provider_api_keys 表 ==========
    op.create_table(
        'provider_api_keys',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('provider_id', sa.String(32), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('encrypted_key', sa.Text(), nullable=False),
        sa.Column('key_suffix', sa.String(4), nullable=False),
        sa.Column('rpm_limit', sa.Integer(), server_default='60', nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )

    # ========== user_api_keys 表 ==========
    op.create_table(
        'user_api_keys',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('key_hash', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('key_prefix', sa.String(12), server_default='ltm-sk-', nullable=False),
        sa.Column('key_suffix', sa.String(4), nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False, index=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
    )

    # ========== request_logs 表 ==========
    op.create_table(
        'request_logs',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('request_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('key_id', sa.String(32), sa.ForeignKey('user_api_keys.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('provider_id', sa.String(32), sa.ForeignKey('providers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('model', sa.String(100), nullable=False, index=True),
        sa.Column('prompt_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('completion_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cost_usd', sa.Numeric(10, 6), server_default='0', nullable=False),
        sa.Column('latency_ms', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(20), server_default='success', nullable=False, index=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, index=True),
    )
    # request_logs 复合索引
    op.create_index('ix_request_logs_user_created', 'request_logs', ['user_id', 'created_at'])
    op.create_index('ix_request_logs_key_created', 'request_logs', ['key_id', 'created_at'])
    op.create_index('ix_request_logs_model_created', 'request_logs', ['model', 'created_at'])

    # ========== monthly_usage 表 ==========
    op.create_table(
        'monthly_usage',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('year_month', sa.String(7), nullable=False),
        sa.Column('total_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_cost_usd', sa.Numeric(10, 4), server_default='0', nullable=False),
        sa.Column('request_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.UniqueConstraint('user_id', 'year_month', name='uq_user_year_month'),
    )
    op.create_index('ix_monthly_usage_year_month', 'monthly_usage', ['year_month'])

    # ========== model_pricing 表 ==========
    op.create_table(
        'model_pricing',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('provider_id', sa.String(32), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('model_name', sa.String(100), nullable=False, index=True),
        sa.Column('input_price_per_1k', sa.Numeric(10, 6), server_default='0', nullable=False),
        sa.Column('output_price_per_1k', sa.Numeric(10, 6), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('model_pricing')
    op.drop_table('monthly_usage')
    op.drop_index('ix_request_logs_model_created', 'request_logs')
    op.drop_index('ix_request_logs_key_created', 'request_logs')
    op.drop_index('ix_request_logs_user_created', 'request_logs')
    op.drop_table('request_logs')
    op.drop_table('user_api_keys')
    op.drop_table('provider_api_keys')
    op.drop_table('providers')
    op.drop_table('users')
