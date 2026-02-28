"""
内置默认定价表

存储各模型的默认定价信息，用于模型发现时匹配
单价单位：USD per 1M tokens
"""

DEFAULT_MODEL_PRICING = {
    # ── Anthropic ──
    "claude-opus-4-20250514": {
        "display_name": "Claude Opus 4",
        "input_price": 15.0000,
        "output_price": 75.0000,
        "context_window": 200000,
        "max_output": 32000,
        "supports_vision": True,
        "supports_tools": True,
    },
    "claude-sonnet-4-20250514": {
        "display_name": "Claude Sonnet 4",
        "input_price": 3.0000,
        "output_price": 15.0000,
        "context_window": 200000,
        "max_output": 64000,
        "supports_vision": True,
        "supports_tools": True,
    },
    "claude-haiku-4-5-20251001": {
        "display_name": "Claude Haiku 4.5",
        "input_price": 0.8000,
        "output_price": 4.0000,
        "context_window": 200000,
        "max_output": 8192,
        "supports_vision": True,
        "supports_tools": True,
    },
    # ── OpenAI ──
    "gpt-4o": {
        "display_name": "GPT-4o",
        "input_price": 2.5000,
        "output_price": 10.0000,
        "context_window": 128000,
        "max_output": 16384,
        "supports_vision": True,
        "supports_tools": True,
    },
    "gpt-4o-mini": {
        "display_name": "GPT-4o Mini",
        "input_price": 0.1500,
        "output_price": 0.6000,
        "context_window": 128000,
        "max_output": 16384,
        "supports_vision": True,
        "supports_tools": True,
    },
    # ── 智谱 GLM ──
    "glm-5": {
        "display_name": "GLM-5",
        "input_price": 0.0000,
        "output_price": 0.0000,
        "context_window": 128000,
        "max_output": 4096,
        "supports_vision": False,
        "supports_tools": True,
    },
    # ── MiniMax ──
    "minimax-m2.5": {
        "display_name": "MiniMax M2.5",
        "input_price": 0.0000,
        "output_price": 0.0000,
        "context_window": 1000000,
        "max_output": 65536,
        "supports_vision": False,
        "supports_tools": True,
    },
}

# Chat 模型过滤策略
CHAT_MODEL_PREFIXES = [
    "gpt-", "o1-", "o3-", "o4-",
    "claude-",
    "glm-",
    "minimax-",
    "qwen-",
    "ernie-",
    "deepseek-",
]

NON_CHAT_KEYWORDS = [
    "embedding", "embed",
    "tts", "whisper", "audio",
    "dall-e", "image",
    "moderation",
    "instruct",
]


def is_chat_model(model_id: str) -> bool:
    """
    判断一个模型 ID 是否为 Chat 模型

    Args:
        model_id: 模型 ID

    Returns:
        是否为 Chat 模型
    """
    model_lower = model_id.lower()

    # 排除非聊天模型关键词
    if any(kw in model_lower for kw in NON_CHAT_KEYWORDS):
        return False

    # 检查聊天模型前缀
    if any(model_lower.startswith(prefix) for prefix in CHAT_MODEL_PREFIXES):
        return True

    return False


def get_default_pricing(model_id: str) -> dict | None:
    """
    获取模型的默认定价信息

    Args:
        model_id: 模型 ID

    Returns:
        定价信息字典，如果模型不在默认列表中则返回 None
    """
    return DEFAULT_MODEL_PRICING.get(model_id)


def has_confirmed_pricing(model_id: str) -> bool:
    """
    检查模型是否有确认的定价

    Args:
        model_id: 模型 ID

    Returns:
        是否有确认的定价（在默认列表中且 input_price > 0）
    """
    pricing = get_default_pricing(model_id)
    if pricing is None:
        return False
    return pricing.get("input_price", 0) > 0
