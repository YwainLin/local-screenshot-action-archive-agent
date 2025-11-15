from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from ..storage.models import Asset, ScanRun, ScanStatus


class ScannerService:
    """目录扫描服务"""

    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

    def __init__(self, db: Session) -> None:
        self.db = db

    def scan_directory(
        self,
        root_path: str | Path,
        allowed_extensions: Optional[List[str]] = None,
    ) -> ScanRun:
        """扫描指定目录，建立只读索引"""
        root_path = Path(root_path).resolve()
        if not root_path.is_dir():
            raise ValueError(f"目录不存在: {root_path}")

        extensions = set(allowed_extensions or self.ALLOWED_EXTENSIONS)

        scan_run = ScanRun(
            id=str(uuid4()),
            root_path=str(root_path),
            status=ScanStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.db.add(scan_run)
        self.db.flush()

        total_files = 0
        error_count = 0
        error_list = []

        for file_path in self._walk_directory(root_path):
            try:
                if file_path.suffix.lower() not in extensions:
                    continue

                stat = file_path.stat()
                asset = Asset(
                    id=str(uuid4()),
                    scan_run_id=scan_run.id,
                    path=str(file_path),
                    filename=file_path.name,
                    extension=file_path.suffix.lower(),
                    sha256="",  # 将在 fingerprint 阶段计算
                    size=stat.st_size,
                    mtime=datetime.fromtimestamp(stat.st_mtime),
                    created_at=datetime.utcnow(),
                )
                self.db.add(asset)
                total_files += 1
            except (PermissionError, OSError) as e:
                error_count += 1
                error_list.append({"path": str(file_path), "error": str(e)})

        scan_run.total_files = total_files
        scan_run.error_count = error_count
        scan_run.error_list = str(error_list)
        scan_run.status = ScanStatus.COMPLETED
        scan_run.completed_at = datetime.utcnow()

        self.db.commit()
        return scan_run

    def _walk_directory(self, root: Path) -> List[Path]:
        """递归遍历目录，返回所有文件路径"""
        files = []
        try:
            for entry in os.scandir(root):
                if entry.is_file(follow_symlinks=False):
                    files.append(Path(entry.path))
                elif entry.is_dir(follow_symlinks=False):
                    files.extend(self._walk_directory(Path(entry.path)))
        except PermissionError:
            pass
        return files

    def get_scan_run(self, scan_run_id: str) -> Optional[ScanRun]:
        """获取扫描任务"""
        return self.db.query(ScanRun).filter(ScanRun.id == scan_run_id).first()

    def get_assets_by_scan_run(
        self, scan_run_id: str, limit: int = 100, offset: int = 0
    ) -> List[Asset]:
        """获取扫描任务的资产列表"""
        return (
            self.db.query(Asset)
            .filter(Asset.scan_run_id == scan_run_id)
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_assets_by_scan_run(self, scan_run_id: str) -> int:
        """统计扫描任务的资产数量"""
        return self.db.query(Asset).filter(Asset.scan_run_id == scan_run_id).count()
