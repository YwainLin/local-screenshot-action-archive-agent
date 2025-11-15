"""规则提取服务单元测试"""

import pytest

from app.services.extractor import (
    ActionPhraseExtractionRule,
    AmountExtractionRule,
    DateExtractionRule,
    ExtractorService,
    SensitivePatternDetector,
    UrlExtractionRule,
)
from app.storage.models import Extraction, OcrResult


@pytest.fixture
def extractor():
    """创建提取服务实例"""
    return ExtractorService()


@pytest.fixture
def sensitive_detector():
    """创建敏感内容检测器"""
    return SensitivePatternDetector()


class TestDateExtractionRule:
    """日期提取规则测试"""

    def test_extract_date_formats(self):
        """测试提取多种日期格式"""
        rule = DateExtractionRule()
        text = "截止日期：2024-01-15，请在2024年1月20日前完成。预约时间：1月25日"

        results = rule.extract(text)

        assert len(results) >= 3
        values = [r["value"] for r in results]
        assert "2024-01-15" in values
        assert "2024年1月20日" in values or "2024年1月20" in values

    def test_extract_no_date(self):
        """测试无日期文本"""
        rule = DateExtractionRule()
        text = "这是一个没有日期的文本"

        results = rule.extract(text)
        assert len(results) == 0


class TestUrlExtractionRule:
    """URL 提取规则测试"""

    def test_extract_urls(self):
        """测试提取 URL"""
        rule = UrlExtractionRule()
        text = "请访问 https://example.com 或 www.test.com 获取更多信息"

        results = rule.extract(text)

        assert len(results) >= 2
        values = [r["value"] for r in results]
        assert any("example.com" in v for v in values)
        assert any("test.com" in v for v in values)

    def test_extract_no_url(self):
        """测试无 URL 文本"""
        rule = UrlExtractionRule()
        text = "这是一个没有链接的文本"

        results = rule.extract(text)
        assert len(results) == 0


class TestAmountExtractionRule:
    """金额提取规则测试"""

    def test_extract_amounts(self):
        """测试提取金额"""
        rule = AmountExtractionRule()
        text = "商品价格 ¥199.00，运费 10元，总计金额：209.00"

        results = rule.extract(text)

        assert len(results) >= 2
        values = [r["value"] for r in results]
        assert any("199" in v for v in values)

    def test_extract_no_amount(self):
        """测试无金额文本"""
        rule = AmountExtractionRule()
        text = "这是一个没有金额的文本"

        results = rule.extract(text)
        assert len(results) == 0


class TestActionPhraseExtractionRule:
    """行动词提取规则测试"""

    def test_extract_action_phrases(self):
        """测试提取行动词"""
        rule = ActionPhraseExtractionRule()
        text = "截止日期：2024-01-15，请在待处理：订单确认后领取时间：明天上午"

        results = rule.extract(text)

        assert len(results) >= 2

    def test_extract_no_action(self):
        """测试无行动词文本"""
        rule = ActionPhraseExtractionRule()
        text = "这是一个没有行动词的文本"

        results = rule.extract(text)
        assert len(results) == 0


class TestSensitivePatternDetector:
    """敏感内容检测器测试"""

    def test_detect_otp(self, sensitive_detector):
        """测试检测验证码"""
        text = "您的验证码是 123456，请勿泄露"
        results = sensitive_detector.detect_otp(text)

        assert len(results) >= 1
        assert results[0]["type"] == "otp"

    def test_detect_bank_card(self, sensitive_detector):
        """测试检测银行卡号"""
        text = "银行卡号：6222021234567890123"
        results = sensitive_detector.detect_bank_card(text)

        assert len(results) >= 1
        assert results[0]["type"] == "bank_card"

    def test_detect_phone(self, sensitive_detector):
        """测试检测电话号码"""
        text = "联系电话：13812345678"
        results = sensitive_detector.detect_phone(text)

        assert len(results) >= 1
        assert results[0]["type"] == "phone"

    def test_detect_id_card(self, sensitive_detector):
        """测试检测身份证号"""
        text = "身份证号：110101199001011234"
        results = sensitive_detector.detect_id_card(text)

        assert len(results) >= 1
        assert results[0]["type"] == "id_card"

    def test_detect_all(self, sensitive_detector):
        """测试检测所有敏感内容"""
        text = "验证码 123456，电话 13812345678"
        results = sensitive_detector.detect_all(text)

        assert len(results) >= 2
        types = {r["type"] for r in results}
        assert "otp" in types
        assert "phone" in types


class TestExtractorService:
    """提取服务测试"""

    def test_extract_from_text(self, extractor):
        """测试从文本提取实体"""
        text = "截止日期：2024-01-15，商品价格 ¥199.00，请访问 https://example.com"

        extractions = extractor.extract_from_text(text, "asset-1")

        assert len(extractions) >= 2
        for ext in extractions:
            assert isinstance(ext, Extraction)
            assert ext.asset_id == "asset-1"
            assert ext.kind in ["date", "url", "amount", "action_phrase"]

    def test_extract_from_ocr_result(self, extractor):
        """测试从 OCR 结果提取实体"""
        ocr_result = OcrResult(
            id="ocr-1",
            asset_id="asset-1",
            engine="test",
            language="ch",
            text="截止日期：2024-01-15，商品价格 ¥199.00",
            confidence=0.9,
        )

        extractions = extractor.extract_from_ocr_result(ocr_result)

        assert len(extractions) >= 2
        for ext in extractions:
            assert ext.ocr_result_id == "ocr-1"

    def test_extract_empty_text(self, extractor):
        """测试提取空文本"""
        extractions = extractor.extract_from_text("", "asset-1")
        assert len(extractions) == 0

    def test_mask_sensitive_text(self, extractor):
        """测试敏感内容掩码"""
        text = "验证码是 123456，电话 13812345678"

        masked = extractor.mask_sensitive_text(text)

        assert "123456" not in masked
        assert "13812345678" not in masked
        assert "***" in masked or "****" in masked

    def test_mask_no_sensitive(self, extractor):
        """测试无敏感内容时不掩码"""
        text = "这是一个普通文本"

        masked = extractor.mask_sensitive_text(text)

        assert masked == text
