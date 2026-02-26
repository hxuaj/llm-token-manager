"""
OpenRouter 适配器

OpenRouter 是一个统一的 LLM API 网关，支持多种模型
API 文档: https://openrouter.ai/docs
"""
import os
from typing import Dict, Any, AsyncGenerator
import httpx

from services.providers.base import BaseAdapter


class OpenRouterAdapter(BaseAdapter):
    """OpenRouter 适配器 - OpenAI 兼容格式"""

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        super().__init__(api_key, base_url)

    def get_headers(self) -> Dict[str, str]:
        """
        获取 OpenRouter 请求头

        OpenRouter 需要额外的头部信息用于排行榜
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # 可选：添加站点信息用于 OpenRouter 排行榜
        # 可以通过环境变量配置
        site_url = os.getenv("OPENROUTER_SITE_URL", "http://localhost:3000")
        site_name = os.getenv("OPENROUTER_SITE_NAME", "LLM Token Manager")

        if site_url:
            headers["HTTP-Referer"] = site_url
        if site_name:
            headers["X-Title"] = site_name

        return headers

    def convert_request(self, openai_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        OpenRouter 使用 OpenAI 兼容格式，无需转换

        支持的模型格式示例：
        - openai/gpt-4o
        - anthropic/claude-sonnet-4
        - google/gemini-pro-1.5
        - meta-llama/llama-3-70b-instruct
        - deepseek/deepseek-chat
        """
        return openai_request

    def convert_response(self, provider_response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """OpenRouter 返回 OpenAI 兼容格式，无需转换"""
        return provider_response

    async def forward_request(
        self,
        request: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """转发请求到 OpenRouter"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.get_endpoint(),
                headers=self.get_headers(),
                json=request
            )
            response.raise_for_status()
            return response.json()

    async def forward_stream(
        self,
        request: Dict[str, Any]
    ) -> AsyncGenerator[bytes, None]:
        """转发流式请求到 OpenRouter"""
        request["stream"] = True

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                self.get_endpoint(),
                headers=self.get_headers(),
                json=request
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk
