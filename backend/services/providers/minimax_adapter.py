"""
MiniMax 适配器

MiniMax 使用 Anthropic 兼容 API 格式
Base URL: https://api.minimaxi.com/anthropic

注意：MiniMax 不支持以下参数（会被忽略）：
- top_k
- stop_sequences
- service_tier
- mcp_servers
- context_management
- container

MiniMax 不支持以下消息类型：
- image
- document
"""
from typing import Dict, Any
from services.providers.anthropic_adapter import AnthropicAdapter


class MiniMaxAdapter(AnthropicAdapter):
    """MiniMax 适配器 - 继承 Anthropic 适配器并处理 MiniMax 特定限制"""

    @property
    def provider_name(self) -> str:
        return "minimax"

    def convert_request(self, openai_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 OpenAI 格式转换为 MiniMax 兼容的 Anthropic 格式

        移除 MiniMax 不支持的参数
        """
        # 先调用父类转换
        anthropic_request = super().convert_request(openai_request)

        # 移除 MiniMax 不支持的参数（虽然文档说会忽略，但为了安全起见移除）
        unsupported_params = [
            "top_k",
            "stop_sequences",
            "service_tier",
            "mcp_servers",
            "context_management",
            "container",
        ]
        for param in unsupported_params:
            anthropic_request.pop(param, None)

        # 确保 messages 不包含 image 或 document 类型
        # MiniMax 只支持 text, tool_use, tool_result, thinking
        if "messages" in anthropic_request:
            anthropic_request["messages"] = self._filter_supported_content(
                anthropic_request["messages"]
            )

        return anthropic_request

    def _filter_supported_content(self, messages: list) -> list:
        """
        过滤消息内容，只保留 MiniMax 支持的类型

        MiniMax 支持：text, tool_use, tool_result, thinking
        MiniMax 不支持：image, document
        """
        supported_types = {"text", "tool_use", "tool_result", "thinking"}

        filtered_messages = []
        for msg in messages:
            content = msg.get("content")

            # 如果 content 是字符串，直接保留
            if isinstance(content, str):
                filtered_messages.append(msg)
            # 如果 content 是列表（多块内容），过滤掉不支持的类型
            elif isinstance(content, list):
                filtered_blocks = []
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type", "text")
                        if block_type in supported_types:
                            filtered_blocks.append(block)
                    else:
                        # 非字典块（如纯文本），保留
                        filtered_blocks.append(block)

                if filtered_blocks:
                    new_msg = msg.copy()
                    new_msg["content"] = filtered_blocks
                    filtered_messages.append(new_msg)
            else:
                # 其他类型直接保留
                filtered_messages.append(msg)

        return filtered_messages
