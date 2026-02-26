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
from models.model_pricing import ModelPricing
from services.encryption import encrypt
from sqlalchemy import select


# OpenRouter 热门模型定价（参考 2026 年 2 月价格）
OPENROUTER_MODELS = [
    # OpenAI models
    {"model_name": "openai/gpt-4o", "input_price": 2.50, "output_price": 10.00},
    {"model_name": "openai/gpt-4o-mini", "input_price": 0.15, "output_price": 0.60},
    {"model_name": "openai/o1-preview", "input_price": 15.00, "output_price": 60.00},
    {"model_name": "openai/o1-mini", "input_price": 1.50, "output_price": 6.00},

    # Anthropic models
    {"model_name": "anthropic/claude-sonnet-4", "input_price": 3.00, "output_price": 15.00},
    {"model_name": "anthropic/claude-3.5-sonnet", "input_price": 3.00, "output_price": 15.00},
    {"model_name": "anthropic/claude-3-haiku", "input_price": 0.25, "output_price": 1.25},

    # Google models
    {"model_name": "google/gemini-pro-1.5", "input_price": 1.25, "output_price": 10.00},
    {"model_name": "google/gemini-flash-1.5", "input_price": 0.075, "output_price": 0.30},

    # DeepSeek models
    {"model_name": "deepseek/deepseek-chat", "input_price": 0.14, "output_price": 0.28},
    {"model_name": "deepseek/deepseek-reasoner", "input_price": 0.55, "output_price": 2.19},

    # Meta Llama models
    {"model_name": "meta-llama/llama-3.3-70b-instruct", "input_price": 0.35, "output_price": 0.40},
    {"model_name": "meta-llama/llama-3.1-405b-instruct", "input_price": 2.00, "output_price": 2.00},

    # Mistral models
    {"model_name": "mistralai/mistral-large", "input_price": 2.00, "output_price": 6.00},

    # Qwen models via OpenRouter
    {"model_name": "qwen/qwen-2.5-72b-instruct", "input_price": 0.35, "output_price": 0.40},

    # xAI Grok
    {"model_name": "x-ai/grok-beta", "input_price": 5.00, "output_price": 15.00},
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

        # 添加模型定价
        added_count = 0
        for model_data in OPENROUTER_MODELS:
            result = await session.execute(
                select(ModelPricing).where(
                    ModelPricing.provider_id == provider.id,
                    ModelPricing.model_name == model_data["model_name"]
                )
            )
            existing_pricing = result.scalar_one_or_none()

            if not existing_pricing:
                from decimal import Decimal
                pricing = ModelPricing(
                    provider_id=provider.id,
                    model_name=model_data["model_name"],
                    input_price_per_1k=Decimal(str(model_data["input_price"])),
                    output_price_per_1k=Decimal(str(model_data["output_price"])),
                )
                session.add(pricing)
                added_count += 1

        await session.commit()
        print(f"添加 {added_count} 个模型定价配置")

        print("\n完成！OpenRouter 供应商已配置。")
        print("\n支持的热门模型：")
        for m in OPENROUTER_MODELS[:5]:
            print(f"  - {m['model_name']}")
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
