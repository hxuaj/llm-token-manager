"""
内置 Provider Loaders

提供常见供应商的自定义加载器：
- AnthropicLoader: 添加 anthropic-version 头和 beta 功能头
- OpenRouterLoader: 添加 referer 头用于来源追踪
"""
from typing import Dict, Any, Optional
import logging

from services.provider_loaders import BaseProviderLoader, register_loader

logger = logging.getLogger(__name__)


@register_loader("anthropic")
class AnthropicLoader(BaseProviderLoader):
    """
    Anthropic Provider Loader

    处理 Anthropic 特有的请求头：
    - x-api-key: API Key 认证
    - anthropic-version: API 版本
    - anthropic-beta: 启用 beta 功能（如 prompt caching）
    """

    # 默认 API 版本
    DEFAULT_API_VERSION = "2023-06-01"

    # Beta 功能头（用于 prompt caching 等）
    BETA_HEADERS = ["prompt-caching-2024-07-31"]

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def get_auth_headers(self, api_key: str) -> Dict[str, str]:
        """
        Anthropic 使用 x-api-key 而非 Bearer token

        Args:
            api_key: Anthropic API Key

        Returns:
            认证请求头
        """
        return {
            "x-api-key": api_key,
            "anthropic-version": self.DEFAULT_API_VERSION,
        }

    def get_extra_headers(
        self,
        original_headers: Dict[str, str],
        request_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        添加 beta 功能头

        如果请求中包含缓存相关的内容（system cache、message cache control），
        则自动添加 prompt-caching beta 头。

        Args:
            original_headers: 原始请求头
            request_data: 请求体数据

        Returns:
            需要添加的额外请求头
        """
        extra_headers = {}

        # 检查是否需要启用 prompt caching
        if request_data and self._has_cache_control(request_data):
            extra_headers["anthropic-beta"] = ",".join(self.BETA_HEADERS)
            logger.debug("Enabled prompt caching beta headers for Anthropic request")

        return extra_headers

    def _has_cache_control(self, request_data: Dict[str, Any]) -> bool:
        """
        检查请求是否包含缓存控制标记

        Args:
            request_data: 请求体数据

        Returns:
            是否包含缓存控制
        """
        # 检查 system 中的 cache_control
        system = request_data.get("system", "")
        if isinstance(system, dict) and system.get("cache_control"):
            return True

        # 检查 messages 中的 cache_control
        messages = request_data.get("messages", [])
        for message in messages:
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("cache_control"):
                            return True

        return False


@register_loader("openrouter")
class OpenRouterLoader(BaseProviderLoader):
    """
    OpenRouter Provider Loader

    处理 OpenRouter 特有的请求头：
    - HTTP-Referer: 来源追踪（可选，用于 OpenRouter 统计）
    - X-Title: 应用名称（可选）
    """

    # 默认 referer（可被配置覆盖）
    DEFAULT_REFERER = "https://llm-token-manager.local"

    # 默认应用名称
    DEFAULT_APP_TITLE = "LLM Token Manager"

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def get_extra_headers(
        self,
        original_headers: Dict[str, str],
        request_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        添加 referer 和应用名称头

        这些头部用于 OpenRouter 统计和追踪请求来源。

        Args:
            original_headers: 原始请求头
            request_data: 请求体数据

        Returns:
            需要添加的额外请求头
        """
        return {
            "HTTP-Referer": self.DEFAULT_REFERER,
            "X-Title": self.DEFAULT_APP_TITLE,
        }


@register_loader("zhipu")
class ZhipuLoader(BaseProviderLoader):
    """
    智谱 AI Provider Loader

    智谱 AI 使用标准的 Bearer token 认证，
    这里暂时不需要特殊处理，仅作为注册占位。
    """

    @property
    def provider_name(self) -> str:
        return "zhipu"


@register_loader("minimax")
class MiniMaxLoader(BaseProviderLoader):
    """
    MiniMax Provider Loader

    MiniMax 使用标准的 OpenAI 兼容格式，
    这里暂时不需要特殊处理，仅作为注册占位。
    """

    @property
    def provider_name(self) -> str:
        return "minimax"
