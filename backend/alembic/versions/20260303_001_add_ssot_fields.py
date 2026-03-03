"""add SSOT fields to providers and model_catalog

Revision ID: 20260303_001
Revises: 20260228_004_batch3_tables
Create Date: 2026-03-03

为 providers 和 model_catalog 表添加 SSOT (Single Source of Truth) 字段，
支持从 models.dev 自动同步模型元数据，同时保留本地覆盖。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision = '20260303_001'
down_revision = 'batch3_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ========== providers 表 ==========
    # 添加 display_name 字段
    op.add_column('providers', sa.Column('display_name', sa.String(100), nullable=True))

    # 添加 source 字段（供应商来源）
    op.add_column('providers', sa.Column(
        'source',
        sa.String(20),
        nullable=False,
        server_default='custom'
    ))

    # 添加 models_dev_id 字段（对应 models.dev 的供应商 ID）
    op.add_column('providers', sa.Column('models_dev_id', sa.String(100), nullable=True))
    op.create_index('ix_providers_models_dev_id', 'providers', ['models_dev_id'])

    # 添加 local_overrides 字段（本地覆盖的字段）
    op.add_column('providers', sa.Column('local_overrides', sa.JSON(), nullable=True, server_default='{}'))

    # 添加 supported_endpoints 字段（支持的端点）
    op.add_column('providers', sa.Column('supported_endpoints', sa.JSON(), nullable=True, server_default='[]'))

    # 添加 last_synced_at 字段（上次同步时间）
    op.add_column('providers', sa.Column('last_synced_at', sa.DateTime(), nullable=True))

    # ========== model_catalog 表 ==========
    # 添加 models_dev_id 字段
    op.add_column('model_catalog', sa.Column('models_dev_id', sa.String(100), nullable=True))
    op.create_index('ix_model_catalog_models_dev_id', 'model_catalog', ['models_dev_id'])

    # 添加 base_config 字段（models.dev 原始配置）
    op.add_column('model_catalog', sa.Column('base_config', sa.JSON(), nullable=True))

    # 添加 local_overrides 字段
    op.add_column('model_catalog', sa.Column('local_overrides', sa.JSON(), nullable=True, server_default='{}'))

    # 添加 last_synced_at 字段
    op.add_column('model_catalog', sa.Column('last_synced_at', sa.DateTime(), nullable=True))

    # 添加扩展能力字段
    op.add_column('model_catalog', sa.Column('supports_reasoning', sa.Boolean(), nullable=False, server_default='0'))

    # 添加元数据字段
    op.add_column('model_catalog', sa.Column('family', sa.String(50), nullable=True))
    op.add_column('model_catalog', sa.Column('knowledge_cutoff', sa.String(20), nullable=True))
    op.add_column('model_catalog', sa.Column('release_date', sa.String(20), nullable=True))

    # 初始化现有数据的 display_name
    op.execute("UPDATE providers SET display_name = name WHERE display_name IS NULL")

    # 初始化现有数据的 source
    op.execute("UPDATE providers SET source = 'custom' WHERE source IS NULL OR source = ''")


def downgrade() -> None:
    # ========== providers 表 ==========
    op.drop_column('providers', 'last_synced_at')
    op.drop_column('providers', 'supported_endpoints')
    op.drop_column('providers', 'local_overrides')
    op.drop_index('ix_providers_models_dev_id', 'providers')
    op.drop_column('providers', 'models_dev_id')
    op.drop_column('providers', 'source')
    op.drop_column('providers', 'display_name')

    # ========== model_catalog 表 ==========
    op.drop_column('model_catalog', 'release_date')
    op.drop_column('model_catalog', 'knowledge_cutoff')
    op.drop_column('model_catalog', 'family')
    op.drop_column('model_catalog', 'supports_reasoning')
    op.drop_column('model_catalog', 'last_synced_at')
    op.drop_column('model_catalog', 'local_overrides')
    op.drop_column('model_catalog', 'base_config')
    op.drop_index('ix_model_catalog_models_dev_id', 'model_catalog')
    op.drop_column('model_catalog', 'models_dev_id')
