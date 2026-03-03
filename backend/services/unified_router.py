"""
统一路由服务

合并 OpenAI 格式和 Anthropic 格式的路由规则，
支持：
- 隐式前缀匹配（gpt-4o -> openai）
- 显式 provider/model 格式（openai/gpt-4o -> openai, gpt-4o）
- 端点级别的适配器选择
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.provider import Provider
from services.providers.base import BaseAdapter
from services.providers.openai_compatible import OpenAICompatibleAdapter
from services.providers.anthropic_adapter import AnthropicAdapter
from services.providers.anthropic_passthrough import AnthropicPassthroughAdapter


@dataclass
class RouteRule:
    """路由规则"""
    provider_name: str
    prefixes: List[str]
    api_format: str  # "openai", "anthropic", "openai_compatible"
    supported_endpoints: List[str]  # ["openai"], ["openai", "anthropic"]
    default_base_url: str = ""
    default_headers: Dict[str, str] = None

    def __post_init__(self):
        if self.default_headers is None:
            self.default_headers = {}


class UnifiedRouterService:
    """
    统一模型路由服务

    替代原有的 MODEL_PREFIX_TO_PROVIDER 和 ANTHROPIC_MODEL_ROUTE_RULES，
    提供统一的路由规则管理。
    """

    # 统一的路由规则
    ROUTE_RULES: Dict[str, RouteRule] = {
        "openai": RouteRule(
            provider_name="openai",
            prefixes=["gpt-", "o1-", "o3-", "o4-"],
            api_format="openai",
            supported_endpoints=["openai"],
            default_base_url="https://api.openai.com/v1",
        ),
        "anthropic": RouteRule(
            provider_name="anthropic",
            prefixes=["claude-"],
            api_format="anthropic",
            supported_endpoints=["openai", "anthropic"],
            default_base_url="https://api.anthropic.com",
            default_headers={"anthropic-version": "2023-06-01"},
        ),
        "zhipu": RouteRule(
            provider_name="zhipu",
            prefixes=["glm-"],
            api_format="openai_compatible",
            supported_endpoints=["openai", "anthropic"],
            default_base_url="https://open.bigmodel.cn/api/paas/v4",
        ),
        "deepseek": RouteRule(
            provider_name="deepseek",
            prefixes=["deepseek-"],
            api_format="openai_compatible",
            supported_endpoints=["openai"],
            default_base_url="https://api.deepseek.com",
        ),
        "minimax": RouteRule(
            provider_name="minimax",
            prefixes=["minimax-", "MiniMax-"],
            api_format="openai_compatible",
            supported_endpoints=["openai", "anthropic"],
            default_base_url="https://api.minimax.chat/v1",
        ),
        "openrouter": RouteRule(
            provider_name="openrouter",
            prefixes=["openai/", "anthropic/", "google/", "meta-llama/",
                      "deepseek/", "mistralai/", "qwen/", "01-ai/",
                      "phind/", "codellama/", "nousresearch/", "x-ai/",
                      "perplexity/"],
            api_format="openai_compatible",
            supported_endpoints=["openai"],
            default_base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://ltm.example.com",
                "X-Title": "LTM Gateway"
            },
        ),
        "qwen": RouteRule(
            provider_name="qwen",
            prefixes=["qwen-"],
            api_format="openai_compatible",
            supported_endpoints=["openai"],
            default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    }

    def parse_model_string(self, model: str) -> Tuple[str, str]:
        """
        解析模型字符串

        支持两种格式：
        1. 隐式格式：通过前缀匹配供应商（gpt-4o -> openai）
        2. 显式格式：provider/model（openai/gpt-4o -> openai, gpt-4o）

        Args:
            model: 模型名称

        Returns:
            (provider_name, model_id)

        Raises:
            ValueError: 无法识别的模型
        """
        # 显式格式: provider/model
        if "/" in model:
            parts = model.split("/", 1)
            provider_name = parts[0]
            model_id = parts[1]
            return provider_name, model_id

        # 隐式格式: 通过前缀匹配
        for provider_name, rule in self.ROUTE_RULES.items():
            for prefix in rule.prefixes:
                if model.startswith(prefix):
                    return provider_name, model

        raise ValueError(f"Unknown model: {model}")

    def supports_endpoint(self, provider_name: str, endpoint: str) -> bool:
        """
        检查供应商是否支持指定的 API 端点格式

        Args:
            provider_name: 供应商名称
            endpoint: "openai" 或 "anthropic"

        Returns:
            是否支持
        """
        rule = self.ROUTE_RULES.get(provider_name)
        if not rule:
            return False
        return endpoint in rule.supported_endpoints

    def get_route_rule(self, provider_name: str) -> Optional[RouteRule]:
        """
        获取供应商的路由规则

        Args:
            provider_name: 供应商名称

        Returns:
            路由规则，不存在则返回 None
        """
        return self.ROUTE_RULES.get(provider_name)

    def create_adapter(
        self,
        provider: Provider,
        api_key: str,
        endpoint: str
    ) -> BaseAdapter:
        """
        根据供应商和端点创建适配器

        规则：
        - OpenAI 端点 + Anthropic 供应商 -> AnthropicAdapter（格式转换）
        - OpenAI 端点 + OpenAI 兼容供应商 -> OpenAICompatibleAdapter（透传）
        - Anthropic 端点 -> AnthropicPassthroughAdapter（透传）

        Args:
            provider: 供应商对象
            api_key: 解密后的 API Key
            endpoint: "openai" 或 "anthropic"

        Returns:
            适配器实例

        Raises:
            ValueError: 不支持的端点
        """
        # 获取路由规则（使用 provider.name 或默认规则）
        rule = self.ROUTE_RULES.get(provider.name)
        api_format = provider.api_format or (rule.api_format if rule else "openai_compatible")

        # 获取自定义 headers
        default_headers = {}
        if rule and rule.default_headers:
            default_headers = rule.default_headers.copy()
        if provider.config:
            # provider.config 可能包含额外的 headers
            pass

        # Anthropic 端点 -> 使用透传适配器
        if endpoint == "anthropic":
            return AnthropicPassthroughAdapter(
                base_url=provider.base_url,
                api_key=api_key,
                default_headers=default_headers
            )

        # OpenAI 端点
        if endpoint == "openai":
            # Anthropic 供应商 -> 使用格式转换适配器
            if api_format == "anthropic":
                # AnthropicAdapter 目前不支持 default_headers
                return AnthropicAdapter(
                    base_url=provider.base_url,
                    api_key=api_key
                )
            # 其他供应商 -> 使用 OpenAI 兼容适配器
            else:
                return OpenAICompatibleAdapter(
                    base_url=provider.base_url,
                    api_key=api_key,
                    default_headers=default_headers
                )

        raise ValueError(f"Unsupported endpoint: {endpoint}")

    async def get_provider_by_name(
        self,
        provider_name: str,
        db: AsyncSession,
        include_disabled: bool = False
    ) -> Optional[Provider]:
        """
        通过名称获取供应商

        Args:
            provider_name: 供应商名称
            db: 数据库会话
            include_disabled: 是否包含禁用的供应商

        Returns:
            Provider 对象，不存在则返回 None
        """
        query = select(Provider).where(Provider.name == provider_name)

        if not include_disabled:
            query = query.where(Provider.enabled == True)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    def get_all_route_rules(self) -> Dict[str, RouteRule]:
        """
        获取所有路由规则

        Returns:
            路由规则字典
        """
        return self.ROUTE_RULES.copy()


# 单例实例
_unified_router: Optional[UnifiedRouterService] = None


def get_unified_router() -> UnifiedRouterService:
    """获取统一路由服务实例"""
    global _unified_router
    if _unified_router is None:
        _unified_router = UnifiedRouterService()
    return _unified_router
