"""
模型变体解析服务

解析模型字符串中的变体信息，如 `claude-sonnet-4:extended-thinking`

变体格式：<base_model_id>:<variant>

支持的变体：
- extended-thinking: Claude 扩展思考模式
- max: Claude 最大输出模式
"""
from typing import Optional, List, Tuple, Dict, Any


class ModelVariantsService:
    """
    模型变体解析服务

    解析和处理模型字符串中的变体信息
    """

    # 已知支持的变体映射
    KNOWN_VARIANTS: Dict[str, List[str]] = {
        "claude-sonnet-4": ["extended-thinking", "max"],
        "claude-opus-4": ["extended-thinking", "max"],
        "claude-sonnet-4-20250514": ["extended-thinking", "max"],
        "claude-opus-4-20250514": ["extended-thinking", "max"],
    }

    def parse_model_string(self, model: str) -> Tuple[str, Optional[str]]:
        """
        解析模型字符串，提取基础模型 ID 和变体

        Args:
            model: 模型字符串，如 "gpt-4o" 或 "claude-sonnet-4:extended-thinking"

        Returns:
            元组 (base_model_id, variant)
            - base_model_id: 基础模型 ID
            - variant: 变体名称，如果没有变体则为 None

        Examples:
            >>> service.parse_model_string("gpt-4o")
            ("gpt-4o", None)
            >>> service.parse_model_string("claude-sonnet-4:extended-thinking")
            ("claude-sonnet-4", "extended-thinking")
        """
        if not model:
            return model, None

        if ":" in model:
            parts = model.split(":", 1)
            base_model = parts[0]
            variant = parts[1] if len(parts) > 1 else None
            return base_model, variant

        return model, None

    def is_variant_supported(self, base_model: str, variant: Optional[str]) -> bool:
        """
        检查变体是否受该模型支持

        Args:
            base_model: 基础模型 ID
            variant: 变体名称，None 表示无变体

        Returns:
            True 如果变体受支持，否则 False
            无变体时始终返回 True
        """
        if variant is None:
            return True

        supported = self.KNOWN_VARIANTS.get(base_model, [])
        return variant in supported

    def get_supported_variants(self, base_model: str) -> List[str]:
        """
        获取模型支持的变体列表

        Args:
            base_model: 基础模型 ID

        Returns:
            支持的变体列表，如果不支持任何变体则返回空列表
        """
        return self.KNOWN_VARIANTS.get(base_model, [])

    def normalize_model_string(self, model: str) -> str:
        """
        标准化模型字符串，去除变体部分

        Args:
            model: 模型字符串

        Returns:
            基础模型 ID（去除变体）
        """
        base_model, _ = self.parse_model_string(model)
        return base_model

    def get_model_variant_info(self, model: str) -> Dict[str, Any]:
        """
        获取完整的模型变体信息

        Args:
            model: 模型字符串

        Returns:
            包含以下字段的字典：
            - base_model: 基础模型 ID
            - variant: 变体名称（可能为 None）
            - is_supported: 变体是否受支持
            - supported_variants: 该模型支持的所有变体列表
        """
        base_model, variant = self.parse_model_string(model)
        supported_variants = self.get_supported_variants(base_model)

        return {
            "base_model": base_model,
            "variant": variant,
            "is_supported": self.is_variant_supported(base_model, variant),
            "supported_variants": supported_variants,
        }


# 单例实例
_model_variants_service: Optional[ModelVariantsService] = None


def get_model_variants_service() -> ModelVariantsService:
    """获取模型变体服务实例"""
    global _model_variants_service
    if _model_variants_service is None:
        _model_variants_service = ModelVariantsService()
    return _model_variants_service
