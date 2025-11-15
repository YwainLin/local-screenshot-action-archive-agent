from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    """LLM 提供商"""
    OLLAMA = "ollama"
    OPENAI = "openai"
    CUSTOM = "custom"


class LLMConfig(BaseModel):
    """LLM 配置"""
    provider: LLMProvider = Field(default=LLMProvider.OLLAMA, description="LLM 提供商")
    api_key: Optional[str] = Field(default=None, description="API Key（Ollama 不需要）")
    base_url: str = Field(default="http://localhost:11434", description="API 基础 URL")
    model: str = Field(default="qwen2.5-vl:latest", description="模型名称")
    temperature: float = Field(default=0.3, description="生成温度")
    max_tokens: int = Field(default=2048, description="最大 token 数")
    timeout: int = Field(default=60, description="请求超时时间（秒）")

    @property
    def is_local(self) -> bool:
        """是否为本地模型"""
        return self.provider == LLMProvider.OLLAMA


def get_llm_config() -> LLMConfig:
    """获取 LLM 配置（从环境变量或配置文件）"""
    import os

    provider = os.getenv("LLM_PROVIDER", "ollama")
    api_key = os.getenv("LLM_API_KEY", None)
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    model = os.getenv("LLM_MODEL", "qwen2.5-vl:latest")

    return LLMConfig(
        provider=LLMProvider(provider),
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def save_llm_config(config: LLMConfig, config_path: Path) -> None:
    """保存 LLM 配置到文件"""
    import json

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(mode="json"), f, ensure_ascii=False, indent=2)


def load_llm_config(config_path: Path) -> Optional[LLMConfig]:
    """从文件加载 LLM 配置"""
    import json

    if not config_path.exists():
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return LLMConfig(**data)
