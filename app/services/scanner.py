"""文件扫描服务"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.storage.models import Asset

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class ScannerService:
    """文件扫描服务"""

    def __init__(self, supported_extensions: Optional[set[str]] = None):
        self.supported_extensions = supported_extensions or SUPPORTED_EXTENSIONS

    def list_assets(self, directory: str, scan_run_id: str) -> list[Asset]:
        """扫描目录并返回图片资产列表

        Args:
            directory: 要扫描的目录路径
            scan_run_id: 关联的扫描任务 ID

        Returns:
            Asset 模型列表
        """
        root = Path(directory)
        if not root.exists():
            raise ValueError(f"目录不存在: {directory}")
        if not root.is_dir():
            raise ValueError(f"路径不是目录: {directory}")

        assets = []
        errors = []

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in self.supported_extensions:
                continue

            try:
                asset = self._create_asset(file_path, scan_run_id)
                assets.append(asset)
            except Exception as e:
                error_msg = f"处理文件失败 {file_path}: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)

        return assets

    def _create_asset(self, file_path: Path, scan_run_id: str) -> Asset:
        """创建 Asset 模型"""
        stat = file_path.stat()

        return Asset(
            scan_run_id=scan_run_id,
            path=str(file_path.resolve()),
            filename=file_path.name,
            size=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime),
        )

    def get_file_stats(self, directory: str) -> dict:
        """获取目录文件统计信息

        Returns:
            包含 total_files, supported_files, total_size 等信息的字典
        """
        root = Path(directory)
        if not root.exists():
            raise ValueError(f"目录不存在: {directory}")

        stats = {
            "total_files": 0,
            "supported_files": 0,
            "unsupported_files": 0,
            "total_size": 0,
            "supported_size": 0,
            "extension_counts": {},
        }

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue

            stats["total_files"] += 1
            stat = file_path.stat()
            stats["total_size"] += stat.st_size

            ext = file_path.suffix.lower()
            stats["extension_counts"][ext] = stats["extension_counts"].get(ext, 0) + 1

            if ext in self.supported_extensions:
                stats["supported_files"] += 1
                stats["supported_size"] += stat.st_size
            else:
                stats["unsupported_files"] += 1

        return stats
