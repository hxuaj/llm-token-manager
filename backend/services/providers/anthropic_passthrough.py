"""
Anthropic 透传适配器

用于 Anthropic 格式端点 (/v1/messages) 的原生透传。
适用于：
- Anthropic 官方 API
- 支持 Anthropic 格式的其他供应商（智谱、MiniMax 等）

特性：
- 请求透传（Anthropic 格式）
- 响应透传（Anthropic 格式）
- 正确的请求头（x-api-key, anthropic-version）
- 支持 anthropic-beta 头
"""
from typing import Dict, Any, AsyncGenerator, Optional
import httpx

from services.providers.base import BaseAdapter


class AnthropicPassthroughAdapter(BaseAdapter):
    """
    Anthropic 格式原生透传适配器

    用于 /v1/messages 端点，直接透传 Anthropic 格式的请求和响应。
    """

    # 默认 Anthropic API 版本
    DEFAULT_ANTHROPIC_VERSION = "2023-06-01"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        default_headers: Optional[Dict[str, str]] = None,
        timeout: float = 120.0
    ):
        """
        初始化适配器

        Args:
            base_url: API 基础 URL
            api_key: API Key
            default_headers: 额外的默认请求头（如 anthropic-beta）
            timeout: 请求超时时间（秒）
        """
        super().__init__(base_url, api_key)
        self.default_headers = default_headers or {}
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        """供应商名称"""
        return "anthropic_passthrough"

    def get_endpoint(self) -> str:
        """
        获取 API 端点 URL

        Anthropic Messages API 端点为 /v1/messages

        Returns:
            完整的端点 URL
        """
        return f"{self.base_url}/v1/messages"

    def get_headers(self) -> Dict[str, str]:
        """
        获取请求头

        Anthropic API 使用：
        - x-api-key: API Key
        - anthropic-version: API 版本
        - content-type: application/json

        Returns:
            Anthropic 格式的请求头
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.DEFAULT_ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        # 合并自定义 headers（如 anthropic-beta）
        headers.update(self.default_headers)
        return headers

    def convert_request(self, anthropic_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Anthropic 格式请求无需转换，直接返回

        Args:
            anthropic_request: Anthropic Messages API 请求格式

        Returns:
            原样返回
        """
        return anthropic_request

    def convert_response(
        self,
        provider_response: Dict[str, Any],
        model: str
    ) -> Dict[str, Any]:
        """
        Anthropic 格式响应无需转换，直接返回

        Args:
            provider_response: Anthropic 格式的响应
            model: 原始请求的模型名称

        Returns:
            原样返回
        """
        return provider_response

    async def forward_request(
        self,
        request: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        转发请求到 Anthropic

        Args:
            request: Anthropic 格式请求
            stream: 是否流式请求

        Returns:
            Anthropic 响应

        Raises:
            httpx.HTTPStatusError: HTTP 错误
            httpx.TimeoutException: 请求超时
        """
        headers = self.get_headers()

        if stream:
            request = {**request, "stream": True}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.get_endpoint(),
                headers=headers,
                json=request
            )
            response.raise_for_status()
            return response.json()

    async def forward_stream(
        self,
        request: Dict[str, Any]
    ) -> AsyncGenerator[bytes, None]:
        """
        转发流式请求到 Anthropic

        Args:
            request: Anthropic 格式请求

        Yields:
            SSE 格式的数据块

        Raises:
            httpx.HTTPStatusError: HTTP 错误
            httpx.TimeoutException: 请求超时
        """
        headers = self.get_headers()

        # 确保开启流式
        request = {**request, "stream": True}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                self.get_endpoint(),
                headers=headers,
                json=request
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk
