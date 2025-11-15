from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ExtractionResult:
    """提取结果"""
    kind: str
    value_raw: str
    value_masked: str
    evidence_span: Optional[str] = None
    confidence: float = 0.0
    is_sensitive: bool = False


class RuleExtractor:
    """规则提取器"""

    DATE_PATTERNS = [
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?",
        r"\d{1,2}[-/月]\d{1,2}[日号]",
        r"(\d{4})年(\d{1,2})月(\d{1,2})日",
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
    ]

    URL_PATTERNS = [
        r"https?://[^\s<>\"]+",
        r"www\.[^\s<>\"]+",
        r"[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9]+)+(/[^\s<>\"]*)?",
    ]

    AMOUNT_PATTERNS = [
        r"[¥￥$]\s*\d+(?:\.\d{1,2})?",
        r"\d+(?:\.\d{1,2})?\s*[元块]",
        r"(\d+(?:\.\d{1,2})?)\s*元",
        r"金额[：:]\s*(\d+(?:\.\d{1,2})?)",
    ]

    ACTION_KEYWORDS = [
        "截止", "领取", "预约", "待处理", "待办", "待完成",
        "请", "需要", "必须", "应该", "建议", "提醒",
        "提交", "完成", "处理", "确认", "支付", "购买",
        "下载", "上传", "发送", "回复", "查看", "检查",
    ]

    SENSITIVE_PATTERNS = [
        (r"\d{4}\s*\d{4}\s*\d{4}\s*\d{4}", "card_number"),
        (r"\d{6}(?:\d{2})?", "verification_code"),
        (r"验证码[：:]\s*\d{4,6}", "verification_code"),
        (r"密码[：:].{4,}", "password"),
        (r"\d{18}[\dXx]", "id_card"),
    ]

    def __init__(self) -> None:
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """预编译正则表达式"""
        self.date_regex = [re.compile(p) for p in self.DATE_PATTERNS]
        self.url_regex = [re.compile(p) for p in self.URL_PATTERNS]
        self.amount_regex = [re.compile(p) for p in self.AMOUNT_PATTERNS]
        self.sensitive_regex = [
            (re.compile(p), kind) for p, kind in self.SENSITIVE_PATTERNS
        ]

    def extract_dates(self, text: str) -> List[ExtractionResult]:
        """提取日期"""
        results = []
        seen = set()

        for regex in self.date_regex:
            for match in regex.finditer(text):
                value = match.group(0)
                if value not in seen:
                    seen.add(value)
                    results.append(
                        ExtractionResult(
                            kind="date",
                            value_raw=value,
                            value_masked=self._mask_date(value),
                            evidence_span=self._get_context(text, match.start(), match.end()),
                            confidence=0.9,
                            is_sensitive=False,
                        )
                    )

        return results

    def extract_urls(self, text: str) -> List[ExtractionResult]:
        """提取 URL"""
        results = []
        seen = set()

        for regex in self.url_regex:
            for match in regex.finditer(text):
                value = match.group(0)
                if value not in seen and len(value) > 5:
                    seen.add(value)
                    results.append(
                        ExtractionResult(
                            kind="url",
                            value_raw=value,
                            value_masked=value,
                            evidence_span=self._get_context(text, match.start(), match.end()),
                            confidence=0.85,
                            is_sensitive=False,
                        )
                    )

        return results

    def extract_amounts(self, text: str) -> List[ExtractionResult]:
        """提取金额"""
        results = []
        seen = set()

        for regex in self.amount_regex:
            for match in regex.finditer(text):
                value = match.group(0)
                if value not in seen:
                    seen.add(value)
                    results.append(
                        ExtractionResult(
                            kind="amount_candidate",
                            value_raw=value,
                            value_masked=self._mask_amount(value),
                            evidence_span=self._get_context(text, match.start(), match.end()),
                            confidence=0.8,
                            is_sensitive=False,
                        )
                    )

        return results

    def extract_action_phrases(self, text: str) -> List[ExtractionResult]:
        """提取行动短语"""
        results = []
        sentences = re.split(r"[。！？\n]", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            for keyword in self.ACTION_KEYWORDS:
                if keyword in sentence:
                    results.append(
                        ExtractionResult(
                            kind="action_phrase",
                            value_raw=sentence,
                            value_masked=sentence,
                            evidence_span=sentence,
                            confidence=0.7,
                            is_sensitive=False,
                        )
                    )
                    break

        return results

    def detect_sensitive(self, text: str) -> List[ExtractionResult]:
        """检测敏感信息"""
        results = []
        seen = set()

        for regex, kind in self.sensitive_regex:
            for match in regex.finditer(text):
                value = match.group(0)
                if value not in seen:
                    seen.add(value)
                    results.append(
                        ExtractionResult(
                            kind="sensitive_candidate",
                            value_raw=value,
                            value_masked=self._mask_sensitive(value, kind),
                            evidence_span=self._get_context(text, match.start(), match.end()),
                            confidence=0.9,
                            is_sensitive=True,
                        )
                    )

        return results

    def extract_all(self, text: str) -> List[ExtractionResult]:
        """提取所有类型的信息"""
        results = []
        results.extend(self.extract_dates(text))
        results.extend(self.extract_urls(text))
        results.extend(self.extract_amounts(text))
        results.extend(self.extract_action_phrases(text))
        results.extend(self.detect_sensitive(text))
        return results

    def _get_context(self, text: str, start: int, end: int, window: int = 20) -> str:
        """获取匹配文本的上下文"""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        return text[context_start:context_end]

    def _mask_date(self, value: str) -> str:
        """掩码日期（保留部分）"""
        if len(value) > 8:
            return value[:4] + "****"
        return value

    def _mask_amount(self, value: str) -> str:
        """掩码金额（保留符号）"""
        return re.sub(r"\d+", "***", value)

    def _mask_sensitive(self, value: str, kind: str) -> str:
        """掩码敏感信息"""
        if kind == "card_number":
            return value[:4] + " **** **** " + value[-4:]
        elif kind == "verification_code":
            return "****"
        elif kind == "password":
            return "******"
        elif kind == "id_card":
            return value[:6] + "********" + value[-4:]
        return "***"


def get_rule_extractor() -> RuleExtractor:
    """获取规则提取器实例"""
    return RuleExtractor()
