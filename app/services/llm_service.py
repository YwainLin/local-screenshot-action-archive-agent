from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from ..storage.llm_config import LLMConfig, get_llm_config


class LLMService:
    """LLM 服务封装"""

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or get_llm_config()
        self.client = httpx.Client(timeout=self.config.timeout)

    @property
    def is_available(self) -> bool:
        """检查 LLM 是否可用"""
        try:
            if self.config.provider.value == "ollama":
                response = self.client.get(f"{self.config.base_url}/api/tags")
                return response.status_code == 200
            else:
                return bool(self.config.api_key)
        except Exception:
            return False

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """与 LLM 对话"""
        if self.config.provider.value == "ollama":
            return self._chat_ollama(messages, temperature, max_tokens)
        else:
            return self._chat_openai Compatible(messages, temperature, max_tokens)

    def _chat_ollama(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Ollama API 调用"""
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": max_tokens or self.config.max_tokens,
            },
        }

        response = self.client.post(
            f"{self.config.base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()

        result = response.json()
        return result.get("message", {}).get("content", "")

    def _chat_openai Compatible(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """OpenAI 兼容 API 调用"""
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        response = self.client.post(
            f"{self.config.base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        result = response.json()
        return result["choices"][0]["message"]["content"]

    def generate_title(self, ocr_text: str) -> str:
        """根据 OCR 文本生成标题"""
        messages = [
            {
                "role": "system",
                "content": "你是一个图片标题生成器。根据 OCR 识别的文本，生成一个简短的中文标题（不超过20字）。只输出标题，不要解释。",
            },
            {
                "role": "user",
                "content": f"OCR 文本：{ocr_text[:500]}",
            },
        ]

        try:
            return self.chat(messages, temperature=0.3, max_tokens=50)
        except Exception:
            return ""

    def generate_category(self, ocr_text: str, extractions: List[Dict]) -> str:
        """根据内容生成分类建议"""
        extraction_summary = "\n".join(
            [f"- {e.get('kind', '')}: {e.get('value_masked', '')}" for e in extractions[:5]]
        )

        messages = [
            {
                "role": "system",
                "content": """你是一个图片分类器。根据 OCR 文本和提取的信息，选择一个最合适的分类。
可选分类：时间相关、网络资源、财务相关、待办事项、敏感信息、其他。
只输出分类名称，不要解释。""",
            },
            {
                "role": "user",
                "content": f"OCR 文本：{ocr_text[:500]}\n\n提取信息：\n{extraction_summary}",
            },
        ]

        try:
            return self.chat(messages, temperature=0.3, max_tokens=20)
        except Exception:
            return "其他"

    def analyze_sensitivity(self, ocr_text: str) -> Dict[str, Any]:
        """分析内容敏感性"""
        messages = [
            {
                "role": "system",
                "content": """你是一个内容敏感性分析器。分析文本是否包含敏感信息。
返回 JSON 格式：
{
  "is_sensitive": true/false,
  "sensitivity_level": "low/medium/high",
  "reason": "原因说明"
}""",
            },
            {
                "role": "user",
                "content": f"文本：{ocr_text[:500]}",
            },
        ]

        try:
            response = self.chat(messages, temperature=0.3, max_tokens=100)
            return json.loads(response)
        except Exception:
            return {
                "is_sensitive": False,
                "sensitivity_level": "low",
                "reason": "分析失败",
            }

    def generate_summary(self, ocr_text: str) -> str:
        """生成内容摘要"""
        messages = [
            {
                "role": "system",
                "content": "你是一个摘要生成器。根据 OCR 文本生成一句简短的中文摘要（不超过50字）。只输出摘要。",
            },
            {
                "role": "user",
                "content": f"OCR 文本：{ocr_text[:500]}",
            },
        ]

        try:
            return self.chat(messages, temperature=0.3, max_tokens=100)
        except Exception:
            return ""


def get_llm_service(config: Optional[LLMConfig] = None) -> LLMService:
    """获取 LLM 服务实例"""
    return LLMService(config)
