"""
Provider Loaders 模块

提供自定义的供应商加载器，用于注入特殊的请求头和处理逻辑。
"""
from typing import Dict, Any, Optional, Type, Callable
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


# 注册表
_loader_registry: Dict[str, Type["BaseProviderLoader"]] = {}


def register_loader(loader_id: str):
    """
    注册 loader 装饰器

    Usage:
        @register_loader("anthropic")
        class AnthropicLoader(BaseProviderLoader):
            ...
    """
    def decorator(cls: Type["BaseProviderLoader"]) -> Type["BaseProviderLoader"]:
        _loader_registry[loader_id] = cls
        logger.debug(f"Registered provider loader: {loader_id}")
        return cls
    return decorator


def get_loader(provider_name: str) -> Optional["BaseProviderLoader"]:
    """
    获取供应商的 loader 实例

    Args:
        provider_name: 供应商名称（如 "anthropic", "openrouter"）

    Returns:
        loader 实例或 None
    """
    loader_cls = _loader_registry.get(provider_name)
    if loader_cls:
        return loader_cls()
    return None


def get_all_loaders() -> Dict[str, Type["BaseProviderLoader"]]:
    """获取所有已注册的 loader"""
    return _loader_registry.copy()


class BaseProviderLoader(ABC):
    """
    Provider Loader 基类

    用于在发送请求到上游供应商前注入自定义逻辑：
    - 添加特殊请求头（beta 头、referer 等）
    - 修改请求体
    - 添加认证信息
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """供应商名称"""
        pass

    def get_extra_headers(
        self,
        original_headers: Dict[str, str],
        request_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        获取需要添加的额外请求头

        Args:
            original_headers: 原始请求头
            request_data: 请求体数据（可选）

        Returns:
            需要添加的额外请求头
        """
        return {}

    def modify_request_body(
        self,
        body: Dict[str, Any],
        original_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        修改请求体

        Args:
            body: 原始请求体
            original_headers: 原始请求头（可选）

        Returns:
            修改后的请求体
        """
        return body

    def get_auth_headers(self, api_key: str) -> Dict[str, str]:
        """
        获取认证相关的请求头

        Args:
            api_key: API Key

        Returns:
            认证请求头
        """
        # 默认使用 Bearer token
        return {"Authorization": f"Bearer {api_key}"}


# 导入内置 loaders
from services.provider_loaders.builtin import AnthropicLoader, OpenRouterLoader

__all__ = [
    "BaseProviderLoader",
    "register_loader",
    "get_loader",
    "get_all_loaders",
    "AnthropicLoader",
    "OpenRouterLoader",
]
