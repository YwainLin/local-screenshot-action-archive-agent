"""规则提取服务"""

import logging
import re
from datetime import datetime
from typing import Optional

from app.storage.models import Extraction, OcrResult

logger = logging.getLogger(__name__)


class ExtractionRule:
    """提取规则基类"""

    def __init__(self, kind: str, pattern: re.Pattern):
        self.kind = kind
        self.pattern = pattern

    def extract(self, text: str) -> list[dict]:
        """从文本中提取匹配项

        Args:
            text: 输入文本

        Returns:
            提取结果列表，每个结果包含 value, start, end
        """
        results = []
        for match in self.pattern.finditer(text):
            results.append(
                {
                    "value": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
        return results


class DateExtractionRule(ExtractionRule):
    """日期提取规则"""

    def __init__(self):
        # 支持多种日期格式
        patterns = [
            # 2024-01-01, 2024/01/01, 2024.01.01
            r"\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}",
            # 2024年1月1日, 2024年01月01日
            r"\d{4}年\d{1,2}月\d{1,2}[日号]?",
            # 1月1日, 01月01日
            r"\d{1,2}月\d{1,2}[日号]?",
            # 20240101
            r"(?<!\d)20\d{6}(?!\d)",
        ]
        combined = "|".join(f"({p})" for p in patterns)
        super().__init__("date", re.compile(combined))


class UrlExtractionRule(ExtractionRule):
    """URL 提取规则"""

    def __init__(self):
        pattern = r"https?://[^\s<>\"]+|www\.[^\s<>\"]+"
        super().__init__("url", re.compile(pattern))


class AmountExtractionRule(ExtractionRule):
    """金额提取规则"""

    def __init__(self):
        patterns = [
            # ¥100.00, ￥100.00
            r"[¥￥]\s*\d+(?:,\d{3})*(?:\.\d{1,2})?",
            # 100元, 100.00元
            r"\d+(?:,\d{3})*(?:\.\d{1,2})?\s*元",
            # RMB 100.00
            r"(?:RMB|rmb|人民币)\s*\d+(?:,\d{3})*(?:\.\d{1,2})?",
            # 金额：100.00
            r"金额[：:]\s*\d+(?:,\d{3})*(?:\.\d{1,2})?",
        ]
        combined = "|".join(f"({p})" for p in patterns)
        super().__init__("amount", re.compile(combined))


class ActionPhraseExtractionRule(ExtractionRule):
    """行动词提取规则"""

    def __init__(self):
        patterns = [
            # 截止日期、截止时间
            r"截止[日期时间]*[：:]\s*[^\n,，。；;]+",
            # 预约、预订
            r"预约[时间日期]*[：:]\s*[^\n,，。；;]+",
            # 待处理、待办
            r"待[处理办审核批]*[：:]\s*[^\n,，。；;]+",
            # 领取、提取
            r"领取[时间地点方式]*[：:]\s*[^\n,，。；;]+",
            # 支付、付款
            r"[支付付][款出][金额时间]*[：:]\s*[^\n,，。；;]+",
            # 发货、收货
            r"[发收][货货][状态时间]*[：:]\s*[^\n,，。；;]+",
        ]
        combined = "|".join(f"({p})" for p in patterns)
        super().__init__("action_phrase", re.compile(combined))


class SensitivePatternDetector:
    """敏感内容检测器"""

    def __init__(self):
        # 验证码/OTP 模式
        self.otp_patterns = [
            re.compile(r"验证码[是为：:\s]*(\d{4,6})"),
            re.compile(r"口令[是为：:\s]*(\d{4,6})"),
            re.compile(r"(?:OTP|code)[：:\s]*(\d{4,6})", re.IGNORECASE),
            re.compile(r"\d{4,6}\s*(?:位验证码|位口令)"),
        ]

        # 银行卡号模式
        self.bank_card_patterns = [
            re.compile(r"(?:银行卡|卡号|账号)[：:\s]*(\d{16,19})"),
            re.compile(r"\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{0,3}"),
        ]

        # 电话号码模式
        self.phone_patterns = [
            re.compile(r"(?:电话|手机|联系方式)[：:\s]*(\d{11})"),
            re.compile(r"1[3-9]\d{9}"),
        ]

        # 身份证号模式
        self.id_card_patterns = [
            re.compile(r"(?:身份证|证件号)[：:\s]*(\d{17}[\dXx])"),
            re.compile(r"\d{6}(?:19|20)\d{9}[\dXx]"),
        ]

    def detect_otp(self, text: str) -> list[dict]:
        """检测验证码"""
        results = []
        for pattern in self.otp_patterns:
            for match in pattern.finditer(text):
                results.append(
                    {
                        "type": "otp",
                        "value": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                    }
                )
        return results

    def detect_bank_card(self, text: str) -> list[dict]:
        """检测银行卡号"""
        results = []
        for pattern in self.bank_card_patterns:
            for match in pattern.finditer(text):
                results.append(
                    {
                        "type": "bank_card",
                        "value": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                    }
                )
        return results

    def detect_phone(self, text: str) -> list[dict]:
        """检测电话号码"""
        results = []
        for pattern in self.phone_patterns:
            for match in pattern.finditer(text):
                results.append(
                    {
                        "type": "phone",
                        "value": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                    }
                )
        return results

    def detect_id_card(self, text: str) -> list[dict]:
        """检测身份证号"""
        results = []
        for pattern in self.id_card_patterns:
            for match in pattern.finditer(text):
                results.append(
                    {
                        "type": "id_card",
                        "value": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                    }
                )
        return results

    def detect_all(self, text: str) -> list[dict]:
        """检测所有敏感内容"""
        results = []
        results.extend(self.detect_otp(text))
        results.extend(self.detect_bank_card(text))
        results.extend(self.detect_phone(text))
        results.extend(self.detect_id_card(text))
        return results


class ExtractorService:
    """规则提取服务"""

    def __init__(self):
        self.rules = [
            DateExtractionRule(),
            UrlExtractionRule(),
            AmountExtractionRule(),
            ActionPhraseExtractionRule(),
        ]
        self.sensitive_detector = SensitivePatternDetector()

    def extract_from_text(
        self,
        text: str,
        asset_id: str,
        ocr_result_id: Optional[str] = None,
    ) -> list[Extraction]:
        """从文本中提取实体

        Args:
            text: 输入文本
            asset_id: 关联的资产 ID
            ocr_result_id: 关联的 OCR 结果 ID

        Returns:
            Extraction 模型列表
        """
        extractions = []

        # 检测敏感内容
        sensitive_items = self.sensitive_detector.detect_all(text)
        sensitive_spans = {(item["start"], item["end"]) for item in sensitive_items}

        # 应用提取规则
        for rule in self.rules:
            matches = rule.extract(text)
            for match in matches:
                # 检查是否与敏感内容重叠
                is_sensitive = any(
                    match["start"] < end and match["end"] > start
                    for start, end in sensitive_spans
                )

                # 提取证据片段（前后各 20 个字符）
                evidence_start = max(0, match["start"] - 20)
                evidence_end = min(len(text), match["end"] + 20)
                evidence_span = text[evidence_start:evidence_end]

                extraction = Extraction(
                    asset_id=asset_id,
                    ocr_result_id=ocr_result_id,
                    kind=rule.kind,
                    value=match["value"],
                    value_masked=match["value"],
                    evidence_span=evidence_span,
                    confidence=0.8,
                    is_sensitive=is_sensitive,
                    source="rule",
                )
                extractions.append(extraction)

        logger.debug(f"提取了 {len(extractions)} 个实体")
        return extractions

    def extract_from_ocr_result(
        self,
        ocr_result: OcrResult,
    ) -> list[Extraction]:
        """从 OCR 结果中提取实体

        Args:
            ocr_result: OCR 结果模型

        Returns:
            Extraction 模型列表
        """
        if not ocr_result.text:
            return []

        return self.extract_from_text(
            text=ocr_result.text,
            asset_id=ocr_result.asset_id,
            ocr_result_id=ocr_result.id,
        )

    def mask_sensitive_text(self, text: str) -> str:
        """对敏感内容进行掩码处理

        Args:
            text: 输入文本

        Returns:
            掩码后的文本
        """
        sensitive_items = self.sensitive_detector.detect_all(text)
        if not sensitive_items:
            return text

        # 按位置排序并替换
        result = text
        offset = 0
        for item in sorted(sensitive_items, key=lambda x: x["start"]):
            start = item["start"] + offset
            end = item["end"] + offset
            original = item["value"]

            # 根据类型选择掩码方式
            if item["type"] == "otp":
                masked = f"***{original[-2:]}**"
            elif item["type"] == "bank_card":
                masked = f"**** **** **** {original[-4:]}"
            elif item["type"] == "phone":
                masked = f"{original[:3]}****{original[-4:]}"
            elif item["type"] == "id_card":
                masked = f"****{original[-4:]}**"
            else:
                masked = "**" + original[2:-2] + "**" if len(original) > 4 else "****"

            result = result[:start] + masked + result[end:]
            offset += len(masked) - len(original)

        return result
