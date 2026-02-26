"""
用户 API Key 服务

提供：
- 生成平台 Key（ltm-sk- 前缀）
- Key 哈希（SHA-256）
- Key 验证
"""
import secrets
import hashlib
from typing import Tuple

# Key 前缀
KEY_PREFIX = "ltm-sk-"
# Key 随机部分长度（32 个十六进制字符 = 16 字节）
KEY_RANDOM_LENGTH = 32


def generate_api_key() -> Tuple[str, str, str]:
    """
    生成平台 API Key

    Returns:
        Tuple[str, str, str]: (原始 Key, SHA-256 哈希, 后4位)

    格式: ltm-sk-{32位随机字符}
    示例: ltm-sk-a3f8b2c1d4e56789abcdef0123456789ab
    """
    # 生成 32 位随机十六进制字符串
    random_part = secrets.token_hex(16)  # 16 字节 = 32 个十六进制字符

    # 组合成完整 Key
    raw_key = f"{KEY_PREFIX}{random_part}"

    # 计算哈希
    key_hash = hash_key(raw_key)

    # 提取后 4 位
    key_suffix = random_part[-4:]

    return raw_key, key_hash, key_suffix


def hash_key(key: str) -> str:
    """
    计算 Key 的 SHA-256 哈希

    Args:
        key: 原始 Key 字符串

    Returns:
        SHA-256 哈希值（十六进制字符串）
    """
    return hashlib.sha256(key.encode()).hexdigest()


def verify_key(raw_key: str, key_hash: str) -> bool:
    """
    验证 Key 是否匹配哈希值

    Args:
        raw_key: 原始 Key 字符串
        key_hash: 存储的哈希值

    Returns:
        是否匹配
    """
    return hash_key(raw_key) == key_hash


def extract_key_suffix(key: str) -> str:
    """
    提取 Key 的后 4 位

    Args:
        key: 原始 Key 字符串

    Returns:
        后 4 位字符
    """
    return key[-4:]
