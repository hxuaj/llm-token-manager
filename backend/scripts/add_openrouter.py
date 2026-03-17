#!/usr/bin/env python3
"""
添加 OpenRouter 供应商配置

用法：
    python scripts/add_openrouter.py                    # 只添加供应商
    python scripts/add_openrouter.py --with-key <API_KEY>  # 添加供应商和 Key
"""
import sys
import asyncio
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import async_session_maker, engine
from models.provider import Provider
from models.provider_api_key import ProviderApiKey, ProviderKeyStatus
from models.model_catalog import ModelCatalog, ModelStatus, ModelSource
from services.encryption import encrypt
from sqlalchemy import select


# OpenRouter 热门模型定价（单位：USD per 1M tokens）
OPENROUTER_MODELS = [
    # OpenAI models
    {"model_id": "openai/gpt-4o", "display_name": "GPT-4o", "input_price": 2.50, "output_price": 10.00},
    {"model_id": "openai/gpt-4o-mini", "display_name": "GPT-4o Mini", "input_price": 0.15, "output_price": 0.60},
    {"model_id": "openai/o1-preview", "display_name": "o1 Preview", "input_price": 15.00, "output_price": 60.00},
    {"model_id": "openai/o1-mini", "display_name": "o1 Mini", "input_price": 1.50, "output_price": 6.00},

    # Anthropic models
    {"model_id": "anthropic/claude-sonnet-4", "display_name": "Claude Sonnet 4", "input_price": 3.00, "output_price": 15.00},
    {"model_id": "anthropic/claude-3.5-sonnet", "display_name": "Claude 3.5 Sonnet", "input_price": 3.00, "output_price": 15.00},
    {"model_id": "anthropic/claude-3-haiku", "display_name": "Claude 3 Haiku", "input_price": 0.25, "output_price": 1.25},

    # Google models
    {"model_id": "google/gemini-pro-1.5", "display_name": "Gemini Pro 1.5", "input_price": 1.25, "output_price": 10.00},
    {"model_id": "google/gemini-flash-1.5", "display_name": "Gemini Flash 1.5", "input_price": 0.075, "output_price": 0.30},

    # DeepSeek models
    {"model_id": "deepseek/deepseek-chat", "display_name": "DeepSeek Chat", "input_price": 0.14, "output_price": 0.28},
    {"model_id": "deepseek/deepseek-reasoner", "display_name": "DeepSeek Reasoner", "input_price": 0.55, "output_price": 2.19},

    # Meta Llama models
    {"model_id": "meta-llama/llama-3.3-70b-instruct", "display_name": "Llama 3.3 70B", "input_price": 0.35, "output_price": 0.40},
    {"model_id": "meta-llama/llama-3.1-405b-instruct", "display_name": "Llama 3.1 405B", "input_price": 2.00, "output_price": 2.00},

    # Mistral models
    {"model_id": "mistralai/mistral-large", "display_name": "Mistral Large", "input_price": 2.00, "output_price": 6.00},

    # Qwen models via OpenRouter
    {"model_id": "qwen/qwen-2.5-72b-instruct", "display_name": "Qwen 2.5 72B", "input_price": 0.35, "output_price": 0.40},

    # xAI Grok
    {"model_id": "x-ai/grok-beta", "display_name": "Grok Beta", "input_price": 5.00, "output_price": 15.00},
]


async def add_openrouter_provider(api_key: str = None):
    """添加 OpenRouter 供应商"""
    async with async_session_maker() as session:
        # 检查是否已存在
        result = await session.execute(
            select(Provider).where(Provider.name == "openrouter")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"OpenRouter 供应商已存在 (ID: {existing.id})")
            provider = existing
        else:
            # 创建供应商
            provider = Provider(
                name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                enabled=True,
            )
            session.add(provider)
            await session.commit()
            await session.refresh(provider)
            print(f"创建 OpenRouter 供应商 (ID: {provider.id})")

        # 添加 API Key（如果提供）
        if api_key:
            result = await session.execute(
                select(ProviderApiKey).where(
                    ProviderApiKey.provider_id == provider.id
                )
            )
            existing_key = result.scalar_one_or_none()

            if existing_key:
                print("该供应商已有 API Key")
            else:
                encrypted_key = encrypt(api_key)
                key_suffix = api_key[-4:] if len(api_key) >= 4 else "****"

                new_key = ProviderApiKey(
                    provider_id=provider.id,
                    encrypted_key=encrypted_key,
                    key_suffix=key_suffix,
                    status=ProviderKeyStatus.ACTIVE.value,
                )
                session.add(new_key)
                await session.commit()
                print(f"添加 API Key (后缀: ...{key_suffix})")

        # 添加模型到 ModelCatalog
        from decimal import Decimal
        added_count = 0
        for model_data in OPENROUTER_MODELS:
            result = await session.execute(
                select(ModelCatalog).where(
                    ModelCatalog.model_id == model_data["model_id"]
                )
            )
            existing_model = result.scalar_one_or_none()

            if not existing_model:
                catalog = ModelCatalog(
                    model_id=model_data["model_id"],
                    display_name=model_data["display_name"],
                    provider_id=provider.id,
                    input_price=Decimal(str(model_data["input_price"])),
                    output_price=Decimal(str(model_data["output_price"])),
                    status=ModelStatus.ACTIVE,
                    source=ModelSource.MANUAL,
                    is_pricing_confirmed=True,
                )
                session.add(catalog)
                added_count += 1

        await session.commit()
        print(f"添加 {added_count} 个模型到 ModelCatalog")

        print("\n完成！OpenRouter 供应商已配置。")
        print("\n支持的热门模型：")
        for m in OPENROUTER_MODELS[:5]:
            print(f"  - {m['model_id']}: {m['display_name']}")
        print(f"  ... 共 {len(OPENROUTER_MODELS)} 个模型")


async def main():
    # 确保表存在
    from database import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    api_key = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--with-key":
        api_key = sys.argv[2]

    await add_openrouter_provider(api_key)


if __name__ == "__main__":
    asyncio.run(main())
