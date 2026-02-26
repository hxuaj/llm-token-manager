"""
供应商适配器基类

定义所有供应商适配器必须实现的接口
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, AsyncGenerator, Optional


class BaseAdapter(ABC):
    """供应商适配器基类"""

    def __init__(self, base_url: str, api_key: str):
        """
        初始化适配器

        Args:
            base_url: 供应商 API 基础 URL
            api_key: 供应商 API Key
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """供应商名称"""
        pass

    @abstractmethod
    def convert_request(self, openai_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 OpenAI 格式请求转换为供应商特定格式

        Args:
            openai_request: OpenAI Chat Completions 请求格式

        Returns:
            供应商特定的请求格式
        """
        pass

    @abstractmethod
    def convert_response(self, provider_response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """
        将供应商响应转换为 OpenAI 格式

        Args:
            provider_response: 供应商特定的响应格式
            model: 原始请求的模型名称

        Returns:
            OpenAI Chat Completions 响应格式
        """
        pass

    @abstractmethod
    async def forward_request(
        self,
        request: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        转发请求到供应商

        Args:
            request: 转换后的请求
            stream: 是否流式请求

        Returns:
            供应商响应
        """
        pass

    @abstractmethod
    async def forward_stream(
        self,
        request: Dict[str, Any]
    ) -> AsyncGenerator[bytes, None]:
        """
        转发流式请求到供应商

        Args:
            request: 转换后的请求

        Yields:
            SSE 格式的数据块
        """
        pass

    def get_endpoint(self) -> str:
        """获取 API 端点 URL"""
        return f"{self.base_url}/chat/completions"
