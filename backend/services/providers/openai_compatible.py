"""
通用 OpenAI 兼容适配器

适用于所有兼容 OpenAI API 格式的供应商：
- 智谱 AI (Zhipu)
- 通义千问 (Qwen)
- DeepSeek
- MiniMax
- OpenRouter
- 其他自定义 OpenAI 兼容 API

特性：
- 请求透传（无需转换）
- 响应透传（无需转换）
- 支持自定义请求头
- 支持自定义端点路径
- 支持流式请求
"""
from typing import Dict, Any, AsyncGenerator, Optional
import httpx

from services.providers.base import BaseAdapter


class OpenAICompatibleAdapter(BaseAdapter):
    """
    通用 OpenAI 兼容适配器

    所有 OpenAI 兼容 API 都可以使用此适配器，
    无需为每个供应商单独编写适配器。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        default_headers: Optional[Dict[str, str]] = None,
        endpoint: str = "/chat/completions",
        timeout: float = 120.0
    ):
        """
        初始化适配器

        Args:
            base_url: API 基础 URL
            api_key: API Key
            default_headers: 额外的默认请求头
            endpoint: 端点路径（默认 /chat/completions）
            timeout: 请求超时时间（秒）
        """
        super().__init__(base_url, api_key)
        self.default_headers = default_headers or {}
        self.custom_endpoint = endpoint
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        """供应商名称"""
        return "openai_compatible"

    def convert_request(self, openai_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        OpenAI 兼容 API 无需转换，直接返回

        Args:
            openai_request: OpenAI Chat Completions 请求格式

        Returns:
            原样返回
        """
        return openai_request

    def convert_response(
        self,
        provider_response: Dict[str, Any],
        model: str
    ) -> Dict[str, Any]:
        """
        OpenAI 兼容响应无需转换，直接返回

        Args:
            provider_response: OpenAI 兼容格式的响应
            model: 原始请求的模型名称

        Returns:
            原样返回
        """
        return provider_response

    def get_headers(self) -> Dict[str, str]:
        """
        获取请求头

        Returns:
            包含 Authorization 和 Content-Type 的请求头
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # 合并自定义 headers（可覆盖默认值）
        headers.update(self.default_headers)
        return headers

    def get_endpoint(self) -> str:
        """
        获取 API 端点 URL

        Returns:
            完整的端点 URL
        """
        return f"{self.base_url}{self.custom_endpoint}"

    async def forward_request(
        self,
        request: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        转发请求到供应商

        Args:
            request: OpenAI 格式请求
            stream: 是否流式请求

        Returns:
            供应商响应

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
        转发流式请求到供应商

        Args:
            request: OpenAI 格式请求

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
