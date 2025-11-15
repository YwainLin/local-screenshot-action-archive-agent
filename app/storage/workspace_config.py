from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class WorkspaceConfig(BaseModel):
    """工作区配置模型"""

    workspace_id: str = Field(..., description="工作区唯一标识")
    workspace_root: Path = Field(..., description="工作区根目录路径")
    allowed_directories: List[Path] = Field(
        ..., description="允许扫描的目录白名单（绝对路径）"
    )
    allowed_extensions: List[str] = Field(
        default=[".png", ".jpg", ".jpeg", ".webp"],
        description="允许的图片文件扩展名",
    )
    thumbnail_size: tuple[int, int] = Field(
        default=(256, 256), description="缩略图尺寸"
    )
    near_duplicate_threshold: int = Field(
        default=10, description="近似重复哈希距离阈值"
    )
    ocr_enabled: bool = Field(default=True, description="是否启用 OCR")
    ocr_language: str = Field(default="ch", description="OCR 语言")
    local_model_enabled: bool = Field(
        default=False, description="是否启用本地视觉语言模型"
    )
    export_directory: Optional[Path] = Field(
        default=None, description="导出目录路径"
    )

    @field_validator("workspace_root", "export_directory", mode="before")
    @classmethod
    def resolve_path(cls, v: str | Path | None) -> Path | None:
        if v is None:
            return None
        return Path(v).resolve()

    @field_validator("allowed_directories", mode="before")
    @classmethod
    def resolve_paths(cls, v: list[str | Path]) -> list[Path]:
        return [Path(p).resolve() for p in v]

    @field_validator("allowed_extensions")
    @classmethod
    def normalize_extensions(cls, v: list[str]) -> list[str]:
        return [ext if ext.startswith(".") else f".{ext}" for ext in v]

    model_config = {"json_encoders": {Path: str}}


def create_workspace_config(
    workspace_id: str,
    workspace_root: str | Path,
    allowed_directories: list[str | Path],
    **kwargs,
) -> WorkspaceConfig:
    """创建工作区配置的便捷函数"""
    return WorkspaceConfig(
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        allowed_directories=allowed_directories,
        **kwargs,
    )


def load_config(config_path: Path) -> WorkspaceConfig:
    """从 JSON 文件加载工作区配置"""
    import json

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return WorkspaceConfig(**data)


def save_config(config: WorkspaceConfig, config_path: Path) -> None:
    """保存工作区配置到 JSON 文件"""
    import json

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
