"""
Anthropic 适配器

将 OpenAI 格式转换为 Anthropic Messages API 格式
"""
import json
import time
from typing import Dict, Any, AsyncGenerator, List, Optional
import httpx

from services.providers.base import BaseAdapter


class AnthropicAdapter(BaseAdapter):
    """Anthropic 适配器"""

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def get_endpoint(self) -> str:
        """Anthropic Messages API 端点"""
        return f"{self.base_url}/messages"

    def convert_request(self, openai_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 OpenAI 格式转换为 Anthropic Messages API 格式

        主要差异：
        - messages 格式相同，但需要处理 system 消息
        - 需要 max_tokens 参数
        - model 名称映射

        Args:
            openai_request: OpenAI Chat Completions 请求格式

        Returns:
            Anthropic Messages API 格式
        """
        messages = []
        system_prompt = None

        for msg in openai_request.get("messages", []):
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                system_prompt = content
            elif role in ["user", "assistant"]:
                messages.append({
                    "role": role,
                    "content": content
                })

        # 构建 Anthropic 请求
        anthropic_request = {
            "model": openai_request.get("model", "claude-sonnet-4-20250514"),
            "messages": messages,
            "max_tokens": openai_request.get("max_tokens", 4096),
        }

        if system_prompt:
            anthropic_request["system"] = system_prompt

        # 可选参数映射
        if "temperature" in openai_request:
            anthropic_request["temperature"] = openai_request["temperature"]
        if "top_p" in openai_request:
            anthropic_request["top_p"] = openai_request["top_p"]
        if "stream" in openai_request:
            anthropic_request["stream"] = openai_request["stream"]

        return anthropic_request

    def convert_response(self, provider_response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """
        将 Anthropic 响应转换为 OpenAI 格式

        Args:
            provider_response: Anthropic Messages API 响应格式
            model: 原始请求的模型名称

        Returns:
            OpenAI Chat Completions 响应格式
        """
        # 提取内容
        content = ""
        if "content" in provider_response:
            for block in provider_response["content"]:
                if block.get("type") == "text":
                    content += block.get("text", "")

        # 提取 usage
        usage = provider_response.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        return {
            "id": provider_response.get("id", f"chatcmpl-{int(time.time())}"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop" if provider_response.get("stop_reason") == "end_turn" else "stop"
                }
            ],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens
            }
        }

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
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
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
        转发流式请求到 Anthropic

        Args:
            request: Anthropic 格式请求

        Yields:
            SSE 格式的数据块（已转换为 OpenAI 格式）
        """
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
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
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data:
                            try:
                                event = json.loads(data)
                                # 转换为 OpenAI 格式的 SSE
                                yield self._convert_stream_event(event)
                            except json.JSONDecodeError:
                                continue

    def _convert_stream_event(self, event: Dict[str, Any]) -> bytes:
        """将 Anthropic 流事件转换为 OpenAI 格式"""
        event_type = event.get("type", "")

        if event_type == "content_block_delta":
            delta = event.get("delta", {})
            text = delta.get("text", "")
            openai_chunk = {
                "id": event.get("id", "chatcmpl-stream"),
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": event.get("model", ""),
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": text},
                        "finish_reason": None
                    }
                ]
            }
            return f"data: {json.dumps(openai_chunk)}\n\n".encode()

        elif event_type == "message_stop":
            return b"data: [DONE]\n\n"

        return b""
