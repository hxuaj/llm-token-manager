"""
智谱 AI (Zhipu) 适配器

智谱 API 兼容 OpenAI 格式，可直接透传
"""
import json
from typing import Dict, Any, AsyncGenerator
import httpx

from services.providers.base import BaseAdapter


class ZhipuAdapter(BaseAdapter):
    """智谱 AI 适配器"""

    @property
    def provider_name(self) -> str:
        return "zhipu"

    def convert_request(self, openai_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        智谱 API 兼容 OpenAI 格式，直接返回

        Args:
            openai_request: OpenAI Chat Completions 请求格式

        Returns:
            原样返回
        """
        return openai_request

    def convert_response(self, provider_response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """
        智谱响应格式兼容 OpenAI，直接返回

        Args:
            provider_response: 智谱响应格式
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
        转发请求到智谱

        Args:
            request: OpenAI 格式请求
            stream: 是否流式请求

        Returns:
            智谱响应
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
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
        转发流式请求到智谱

        Args:
            request: OpenAI 格式请求

        Yields:
            SSE 格式的数据块
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        request["stream"] = True

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                self.get_endpoint(),
                headers=headers,
                json=request
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk
