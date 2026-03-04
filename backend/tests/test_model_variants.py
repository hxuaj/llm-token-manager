"""
测试模型变体解析服务

测试：
- 解析标准模型字符串
- 解析带变体的模型字符串（如 claude-sonnet-4:extended-thinking）
- 验证变体是否受支持
"""
import pytest
from services.model_variants import ModelVariantsService


class TestModelVariantsService:
    """模型变体服务测试"""

    def test_parse_model_string_standard(self):
        """测试解析标准模型字符串（无变体）"""
        service = ModelVariantsService()

        # 标准 OpenAI 模型
        base, variant = service.parse_model_string("gpt-4o")
        assert base == "gpt-4o"
        assert variant is None

        # 标准 Anthropic 模型
        base, variant = service.parse_model_string("claude-sonnet-4-20250514")
        assert base == "claude-sonnet-4-20250514"
        assert variant is None

        # 带版本号的模型
        base, variant = service.parse_model_string("gpt-4-turbo-2024-04-09")
        assert base == "gpt-4-turbo-2024-04-09"
        assert variant is None

    def test_parse_model_string_with_variant(self):
        """测试解析带变体的模型字符串"""
        service = ModelVariantsService()

        # Claude extended-thinking 变体
        base, variant = service.parse_model_string("claude-sonnet-4:extended-thinking")
        assert base == "claude-sonnet-4"
        assert variant == "extended-thinking"

        # Claude max 变体
        base, variant = service.parse_model_string("claude-opus-4:max")
        assert base == "claude-opus-4"
        assert variant == "max"

        # 带完整版本号的模型 + 变体
        base, variant = service.parse_model_string("claude-sonnet-4-20250514:extended-thinking")
        assert base == "claude-sonnet-4-20250514"
        assert variant == "extended-thinking"

    def test_parse_model_string_unknown_variant(self):
        """测试解析未知变体"""
        service = ModelVariantsService()

        # 未知变体仍然被解析，但后续验证会失败
        base, variant = service.parse_model_string("gpt-4o:unknown-variant")
        assert base == "gpt-4o"
        assert variant == "unknown-variant"

    def test_parse_model_string_multiple_colons(self):
        """测试包含多个冒号的字符串"""
        service = ModelVariantsService()

        # 只有第一个冒号是分隔符
        base, variant = service.parse_model_string("model:with:colons")
        assert base == "model"
        assert variant == "with:colons"

    def test_is_variant_supported(self):
        """测试变体是否受支持"""
        service = ModelVariantsService()

        # Claude 支持的变体
        assert service.is_variant_supported("claude-sonnet-4", "extended-thinking") is True
        assert service.is_variant_supported("claude-sonnet-4", "max") is True
        assert service.is_variant_supported("claude-opus-4", "extended-thinking") is True
        assert service.is_variant_supported("claude-opus-4", "max") is True

        # Claude 不支持的变体
        assert service.is_variant_supported("claude-sonnet-4", "unknown") is False
        assert service.is_variant_supported("claude-sonnet-4", "streaming") is False

        # OpenAI 模型不支持变体
        assert service.is_variant_supported("gpt-4o", "extended-thinking") is False

    def test_is_variant_supported_without_variant(self):
        """测试无变体时的验证"""
        service = ModelVariantsService()

        # 无变体时始终返回 True
        assert service.is_variant_supported("claude-sonnet-4", None) is True
        assert service.is_variant_supported("gpt-4o", None) is True
        assert service.is_variant_supported("unknown-model", None) is True

    def test_get_supported_variants(self):
        """测试获取模型支持的变体列表"""
        service = ModelVariantsService()

        # Claude Sonnet 4 支持的变体
        variants = service.get_supported_variants("claude-sonnet-4")
        assert "extended-thinking" in variants
        assert "max" in variants

        # Claude Opus 4 支持的变体
        variants = service.get_supported_variants("claude-opus-4")
        assert "extended-thinking" in variants
        assert "max" in variants

        # 不支持变体的模型返回空列表
        variants = service.get_supported_variants("gpt-4o")
        assert variants == []

    def test_normalize_model_string(self):
        """测试模型字符串标准化"""
        service = ModelVariantsService()

        # 无变体的模型保持不变
        normalized = service.normalize_model_string("gpt-4o")
        assert normalized == "gpt-4o"

        # 带变体的模型返回基础模型
        normalized = service.normalize_model_string("claude-sonnet-4:extended-thinking")
        assert normalized == "claude-sonnet-4"

        # 带版本号的模型 + 变体
        normalized = service.normalize_model_string("claude-sonnet-4-20250514:max")
        assert normalized == "claude-sonnet-4-20250514"

    def test_model_variant_info(self):
        """测试获取完整的变体信息"""
        service = ModelVariantsService()

        info = service.get_model_variant_info("claude-sonnet-4:extended-thinking")
        assert info["base_model"] == "claude-sonnet-4"
        assert info["variant"] == "extended-thinking"
        assert info["is_supported"] is True
        assert "extended-thinking" in info["supported_variants"]

        info = service.get_model_variant_info("gpt-4o")
        assert info["base_model"] == "gpt-4o"
        assert info["variant"] is None
        assert info["is_supported"] is True
        assert info["supported_variants"] == []

        info = service.get_model_variant_info("claude-sonnet-4:unknown")
        assert info["base_model"] == "claude-sonnet-4"
        assert info["variant"] == "unknown"
        assert info["is_supported"] is False

    def test_empty_string(self):
        """测试空字符串"""
        service = ModelVariantsService()

        base, variant = service.parse_model_string("")
        assert base == ""
        assert variant is None

    def test_variant_only(self):
        """测试只有变体部分"""
        service = ModelVariantsService()

        base, variant = service.parse_model_string(":variant")
        assert base == ""
        assert variant == "variant"

    def test_case_sensitivity(self):
        """测试大小写敏感性"""
        service = ModelVariantsService()

        # 变体名称区分大小写
        base, variant = service.parse_model_string("claude-sonnet-4:EXTENDED-THINKING")
        assert base == "claude-sonnet-4"
        assert variant == "EXTENDED-THINKING"

        # 大小写不匹配的变体验证
        assert service.is_variant_supported("claude-sonnet-4", "EXTENDED-THINKING") is False
        assert service.is_variant_supported("claude-sonnet-4", "Extended-Thinking") is False
