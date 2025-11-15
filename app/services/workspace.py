"""工作区配置服务"""

import json
from pathlib import Path
from typing import Optional

from app.storage.models import WorkspaceConfig


class WorkspaceService:
    """工作区配置管理服务"""

    def __init__(self, config_dir: str = "."):
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "config.json"

    def load_config(self) -> Optional[WorkspaceConfig]:
        """加载工作区配置"""
        if not self.config_file.exists():
            return None

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return WorkspaceConfig(**data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise ValueError(f"配置文件格式错误: {e}") from e

    def save_config(self, config: WorkspaceConfig) -> None:
        """保存工作区配置"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)

    def create_workspace(
        self,
        workspace_id: str,
        root_path: str,
        allowed_export_paths: Optional[list[str]] = None,
        **kwargs,
    ) -> WorkspaceConfig:
        """创建工作区配置"""
        root = Path(root_path)
        if not root.exists():
            raise ValueError(f"目录不存在: {root_path}")
        if not root.is_dir():
            raise ValueError(f"路径不是目录: {root_path}")

        config = WorkspaceConfig(
            workspace_id=workspace_id,
            root_path=str(root.resolve()),
            allowed_export_paths=allowed_export_paths or [],
            **kwargs,
        )

        self.save_config(config)
        return config

    def validate_path_access(self, config: WorkspaceConfig, target_path: str) -> bool:
        """验证路径访问权限

        检查目标路径是否在白名单目录内，防止路径遍历攻击。
        """
        try:
            target = Path(target_path).resolve()
            root = Path(config.root_path).resolve()

            # 检查是否在根目录内
            if target == root or root in target.parents:
                return True

            # 检查是否在允许的导出路径内
            for export_path in config.allowed_export_paths:
                export = Path(export_path).resolve()
                if target == export or export in target.parents:
                    return True

            return False
        except (ValueError, OSError):
            return False

    def get_workspace_root(self, config: WorkspaceConfig) -> Path:
        """获取工作区根目录"""
        return Path(config.root_path).resolve()

    def get_thumbnails_dir(self, config: WorkspaceConfig) -> Path:
        """获取缩略图目录"""
        return self.get_workspace_root(config) / "thumbnails"

    def get_exports_dir(self, config: WorkspaceConfig) -> Path:
        """获取导出目录"""
        return self.get_workspace_root(config) / "exports"

    def get_audit_dir(self, config: WorkspaceConfig) -> Path:
        """获取审计日志目录"""
        return self.get_workspace_root(config) / "audit"
