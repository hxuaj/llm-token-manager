"""
加密服务

提供 AES-256 加密/解密功能，用于保护供应商 API Key
"""
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from config import get_settings

settings = get_settings()


def _get_key_bytes() -> bytes:
    """
    从配置中获取加密密钥并转换为 32 字节

    AES-256 需要 32 字节密钥
    """
    key = settings.encryption_key
    # 如果密钥不足 32 字节，用 0 填充
    # 如果超过 32 字节，截断
    key_bytes = key.encode('utf-8')[:32]
    if len(key_bytes) < 32:
        key_bytes = key_bytes + b'\x00' * (32 - len(key_bytes))
    return key_bytes


def encrypt(plaintext: str) -> str:
    """
    使用 AES-256-CBC 加密字符串

    Args:
        plaintext: 明文字符串

    Returns:
        Base64 编码的密文（IV + 密文）
    """
    if not plaintext:
        return ""

    key = _get_key_bytes()

    # 生成随机 IV（16 字节）
    import os
    iv = os.urandom(16)

    # PKCS7 填充
    plaintext_bytes = plaintext.encode('utf-8')
    padding_length = 16 - (len(plaintext_bytes) % 16)
    padded_plaintext = plaintext_bytes + bytes([padding_length] * padding_length)

    # 加密
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()

    # 组合 IV 和密文，然后 Base64 编码
    combined = iv + ciphertext
    return base64.b64encode(combined).decode('utf-8')


def decrypt(encrypted: str) -> str:
    """
    解密 AES-256-CBC 加密的字符串

    Args:
        encrypted: Base64 编码的密文（IV + 密文）

    Returns:
        明文字符串
    """
    if not encrypted:
        return ""

    key = _get_key_bytes()

    # Base64 解码
    combined = base64.b64decode(encrypted)

    # 分离 IV 和密文
    iv = combined[:16]
    ciphertext = combined[16:]

    # 解密
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # 移除 PKCS7 填充
    padding_length = padded_plaintext[-1]
    plaintext = padded_plaintext[:-padding_length]

    return plaintext.decode('utf-8')


def extract_key_suffix(api_key: str) -> str:
    """
    提取 API Key 的后 4 位

    Args:
        api_key: API Key 字符串

    Returns:
        后 4 位字符
    """
    return api_key[-4:] if len(api_key) >= 4 else api_key
