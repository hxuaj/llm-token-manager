"""
Anthropic 适配器

将 OpenAI 格式转换为 Anthropic Messages API 格式
"""
import json
import time
import logging
from typing import Dict, Any, AsyncGenerator, List, Optional
import httpx

from services.providers.base import BaseAdapter

logger = logging.getLogger(__name__)


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
        - tools 格式转换

        Args:
            openai_request: OpenAI Chat Completions 请求格式

        Returns:
            Anthropic Messages API 格式
        """
        messages = []
        system_prompt = None

        for msg in openai_request.get("messages", []):
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                system_prompt = content if content else ""
            elif role in ["user", "assistant"]:
                # 处理 assistant 消息中的 tool_calls
                if role == "assistant" and "tool_calls" in msg:
                    # 转换 OpenAI tool_calls 为 Anthropic content blocks
                    content_blocks = []
                    # 只有当 content 是非空字符串时才添加文本块
                    if content and isinstance(content, str) and content.strip():
                        content_blocks.append({"type": "text", "text": content})
                    for tool_call in msg["tool_calls"]:
                        # 安全解析 arguments JSON
                        args_str = tool_call.get("function", {}).get("arguments", "{}")
                        try:
                            args = json.loads(args_str) if args_str else {}
                        except json.JSONDecodeError:
                            args = {}
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tool_call.get("id", ""),
                            "name": tool_call.get("function", {}).get("name", ""),
                            "input": args
                        })
                    messages.append({"role": role, "content": content_blocks})
                elif role == "user" and isinstance(content, list):
                    # 处理多模态内容
                    messages.append({"role": role, "content": content})
                else:
                    # 确保内容是字符串
                    if content is None:
                        content = ""
                    messages.append({"role": role, "content": str(content)})
            elif role == "tool":
                # 转换 tool 响应为 tool_result
                tool_content = content if content else ""
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": str(tool_content)
                    }]
                })

        # 构建 Anthropic 请求
        anthropic_request = {
            "model": openai_request.get("model", "claude-sonnet-4-20250514"),
            "messages": messages,
            "max_tokens": openai_request.get("max_tokens", 4096),
        }

        if system_prompt:
            anthropic_request["system"] = system_prompt

        # 转换 tools 参数
        if "tools" in openai_request:
            anthropic_tools = []
            for tool in openai_request["tools"]:
                if tool.get("type") == "function":
                    func = tool.get("function", {})
                    # name 是必需字段，跳过没有 name 的 tool
                    if not func.get("name"):
                        continue
                    # 确保 input_schema 是有效的 JSON Schema
                    input_schema = func.get("parameters", {})
                    if not input_schema:
                        input_schema = {"type": "object", "properties": {}}

                    anthropic_tool = {
                        "name": func["name"],
                        "input_schema": input_schema
                    }
                    # 只有当 description 非空时才添加
                    if func.get("description"):
                        anthropic_tool["description"] = func["description"]

                    anthropic_tools.append(anthropic_tool)
            if anthropic_tools:
                anthropic_request["tools"] = anthropic_tools

        # 可选参数映射
        if "temperature" in openai_request:
            anthropic_request["temperature"] = openai_request["temperature"]
        if "top_p" in openai_request:
            anthropic_request["top_p"] = openai_request["top_p"]
        if "stream" in openai_request:
            anthropic_request["stream"] = openai_request["stream"]
        # 传递 tool_choice 参数（MiniMax 和 Anthropic 都支持）
        if "tool_choice" in openai_request:
            anthropic_request["tool_choice"] = openai_request["tool_choice"]

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
        # 提取内容和 tool_calls
        content = ""
        tool_calls = []

        if "content" in provider_response:
            for block in provider_response["content"]:
                block_type = block.get("type", "")

                if block_type == "text":
                    content += block.get("text", "")
                elif block_type == "tool_use":
                    tool_calls.append({
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {}))
                        }
                    })

        # 提取 usage
        usage = provider_response.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        # 确定 finish_reason
        stop_reason = provider_response.get("stop_reason", "end_turn")
        if stop_reason == "tool_use":
            finish_reason = "tool_calls"
        elif stop_reason == "end_turn":
            finish_reason = "stop"
        else:
            finish_reason = stop_reason

        # 构建消息
        message = {"role": "assistant"}
        if content:
            message["content"] = content
        if tool_calls:
            message["tool_calls"] = tool_calls

        return {
            "id": provider_response.get("id", f"chatcmpl-{int(time.time())}"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason
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

        # Debug logging
        logger.debug(f"Anthropic request to {self.get_endpoint()}:")
        logger.debug(f"Request body: {json.dumps(request, ensure_ascii=False, indent=2)}")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.get_endpoint(),
                headers=headers,
                json=request
            )
            if response.status_code != 200:
                logger.error(f"Anthropic API error {response.status_code}: {response.text}")
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

        if event_type == "content_block_start":
            # 处理 content_block_start，包括 tool_use
            content_block = event.get("content_block", {})
            block_type = content_block.get("type", "")

            if block_type == "tool_use":
                # 开始 tool_use，转换为 OpenAI 的 tool_calls 格式
                openai_chunk = {
                    "id": event.get("id", "chatcmpl-stream"),
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": event.get("model", ""),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [{
                                    "index": event.get("index", 0),
                                    "id": content_block.get("id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": content_block.get("name", ""),
                                        "arguments": ""
                                    }
                                }]
                            },
                            "finish_reason": None
                        }
                    ]
                }
                return f"data: {json.dumps(openai_chunk)}\n\n".encode()
            # text 类型的 content_block_start 不需要特殊处理
            return b""

        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta" or "text" in delta:
                # 文本内容
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

            elif delta_type == "thinking_delta":
                # MiniMax 思考过程（reasoning），作为普通文本输出
                thinking = delta.get("thinking", "")
                if thinking:
                    openai_chunk = {
                        "id": event.get("id", "chatcmpl-stream"),
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": event.get("model", ""),
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": thinking},
                                "finish_reason": None
                            }
                        ]
                    }
                    return f"data: {json.dumps(openai_chunk)}\n\n".encode()
                return b""

            elif delta_type == "input_json_delta":
                # tool_use 的 JSON 输入增量
                partial_json = delta.get("partial_json", "")
                openai_chunk = {
                    "id": event.get("id", "chatcmpl-stream"),
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": event.get("model", ""),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [{
                                    "index": event.get("index", 0),
                                    "function": {
                                        "arguments": partial_json
                                    }
                                }]
                            },
                            "finish_reason": None
                        }
                    ]
                }
                return f"data: {json.dumps(openai_chunk)}\n\n".encode()

            return b""

        elif event_type == "content_block_stop":
            # content_block 结束，不需要特殊处理
            return b""

        elif event_type == "message_delta":
            # message_delta 包含最终的 stop_reason，发送带 finish_reason 的 chunk
            delta = event.get("delta", {})
            stop_reason = delta.get("stop_reason")

            if stop_reason:
                finish_reason = "stop" if stop_reason == "end_turn" else stop_reason
                if stop_reason == "tool_use":
                    finish_reason = "tool_calls"
                openai_chunk = {
                    "id": "chatcmpl-stream",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": event.get("model", ""),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": finish_reason
                        }
                    ]
                }
                return f"data: {json.dumps(openai_chunk)}\n\n".encode()

        elif event_type == "message_stop":
            return b"data: [DONE]\n\n"

        return b""
