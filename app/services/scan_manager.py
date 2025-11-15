"""扫描任务管理服务"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from app.services.deduplication import DeduplicationService
from app.services.fingerprint import FingerprintService
from app.services.scanner import ScannerService
from app.storage.database import DatabaseManager
from app.storage.models import (
    Asset,
    DuplicateGroup,
    DuplicateKind,
    ScanRun,
    ScanStatus,
)

logger = logging.getLogger(__name__)


class ScanManager:
    """扫描任务管理器"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.scanner = ScannerService()
        self.fingerprint = FingerprintService()
        self.deduplication = DeduplicationService(self.fingerprint)

    @staticmethod
    def _duplicate_kind_from_string(kind_str: str) -> DuplicateKind:
        """从字符串转换为 DuplicateKind 枚举"""
        if kind_str == "exact":
            return DuplicateKind.EXACT
        elif kind_str == "near":
            return DuplicateKind.NEAR
        else:
            raise ValueError(f"未知的重复类型: {kind_str}")

    def create_scan_run(self, root_path: str) -> ScanRun:
        """创建扫描任务

        Args:
            root_path: 扫描目录路径

        Returns:
            创建的 ScanRun 模型
        """
        scan_id = str(uuid.uuid4())
        now = datetime.now()

        scan_run = ScanRun(
            id=scan_id,
            root_path=root_path,
            status=ScanStatus.PENDING,
            started_at=now,
        )

        # 保存到数据库
        self.db_manager.execute(
            """
            INSERT INTO scan_run (id, root_path, status, started_at)
            VALUES (?, ?, ?, ?)
            """,
            (scan_id, root_path, ScanStatus.PENDING.value, now.isoformat()),
        )

        logger.info(f"创建扫描任务: {scan_id}, 目录: {root_path}")
        return scan_run

    def start_scan(self, scan_id: str, phash_threshold: int = 10) -> ScanRun:
        """执行扫描任务

        Args:
            scan_id: 扫描任务 ID
            phash_threshold: 近似重复阈值

        Returns:
            更新后的 ScanRun 模型
        """
        # 获取扫描任务
        scan_run = self.get_scan_run(scan_id)
        if not scan_run:
            raise ValueError(f"扫描任务不存在: {scan_id}")

        if scan_run.status != ScanStatus.PENDING:
            raise ValueError(f"扫描任务状态不允许执行: {scan_run.status}")

        # 更新状态为运行中
        self._update_scan_status(scan_id, ScanStatus.RUNNING)

        try:
            # 扫描文件
            assets = self.scanner.list_assets(scan_run.root_path, scan_id)
            total_files = len(assets)

            # 更新总文件数
            self.db_manager.execute(
                "UPDATE scan_run SET total_files = ? WHERE id = ?",
                (total_files, scan_id),
            )

            # 保存资产到数据库（先保存以获取 ID）
            for asset in assets:
                self._save_asset(asset)

            # 处理指纹和重复检测（此时资产已有 ID）
            duplicate_groups = self.deduplication.process_assets(assets, phash_threshold)

            # 更新资产的指纹信息到数据库
            for asset in assets:
                if asset.id:
                    self.db_manager.execute(
                        """
                        UPDATE asset SET sha256 = ?, phash = ?, width = ?, height = ?
                        WHERE id = ?
                        """,
                        (asset.sha256, asset.phash, asset.width, asset.height, asset.id),
                    )

            # 保存重复组到数据库
            for group in duplicate_groups:
                self._save_duplicate_group(group)

            # 更新扫描完成状态
            self._update_scan_status(scan_id, ScanStatus.COMPLETED)

            # 返回更新后的扫描任务
            scan_run = self.get_scan_run(scan_id)
            scan_run.total_files = total_files
            scan_run.scanned_files = total_files

            logger.info(
                f"扫描完成: {scan_id}, 文件数: {total_files}, "
                f"重复组: {len(duplicate_groups)}"
            )
            return scan_run

        except Exception as e:
            # 更新失败状态
            self._update_scan_status(scan_id, ScanStatus.FAILED)
            self._add_scan_error(scan_id, str(e))
            raise

    def get_scan_run(self, scan_id: str) -> Optional[ScanRun]:
        """获取扫描任务

        Args:
            scan_id: 扫描任务 ID

        Returns:
            ScanRun 模型，不存在则返回 None
        """
        row = self.db_manager.fetchone(
            "SELECT * FROM scan_run WHERE id = ?", (scan_id,)
        )
        if not row:
            return None

        return ScanRun(
            id=row["id"],
            root_path=row["root_path"],
            status=ScanStatus(row["status"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            total_files=row["total_files"],
            scanned_files=row["scanned_files"],
            error_count=row["error_count"],
            error_messages=json.loads(row["error_messages"]) if row["error_messages"] else [],
        )

    def list_scan_runs(self, limit: int = 50) -> list[ScanRun]:
        """列出扫描任务

        Args:
            limit: 返回数量限制

        Returns:
            ScanRun 模型列表
        """
        rows = self.db_manager.fetchall(
            "SELECT * FROM scan_run ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )

        return [
            ScanRun(
                id=row["id"],
                root_path=row["root_path"],
                status=ScanStatus(row["status"]),
                started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                total_files=row["total_files"],
                scanned_files=row["scanned_files"],
                error_count=row["error_count"],
                error_messages=json.loads(row["error_messages"]) if row["error_messages"] else [],
            )
            for row in rows
        ]

    def get_assets_by_scan(self, scan_id: str) -> list[Asset]:
        """获取扫描任务的所有资产

        Args:
            scan_id: 扫描任务 ID

        Returns:
            Asset 模型列表
        """
        rows = self.db_manager.fetchall(
            "SELECT * FROM asset WHERE scan_run_id = ?",
            (scan_id,),
        )

        return [
            Asset(
                id=row["id"],
                scan_run_id=row["scan_run_id"],
                path=row["path"],
                filename=row["filename"],
                sha256=row["sha256"],
                phash=row["phash"],
                size=row["size"],
                mtime=datetime.fromisoformat(row["mtime"]),
                width=row["width"],
                height=row["height"],
                thumbnail_path=row["thumbnail_path"],
            )
            for row in rows
        ]

    def get_duplicate_groups(self, scan_id: str) -> list[DuplicateGroup]:
        """获取扫描任务的重复组

        Args:
            scan_id: 扫描任务 ID

        Returns:
            DuplicateGroup 模型列表
        """
        rows = self.db_manager.fetchall(
            "SELECT * FROM duplicate_group WHERE scan_run_id = ?",
            (scan_id,),
        )

        groups = []
        for row in rows:
            # 获取组内资产
            asset_rows = self.db_manager.fetchall(
                """
                SELECT asset_id FROM duplicate_group_asset
                WHERE group_id = ?
                """,
                (row["id"],),
            )
            asset_ids = [r["asset_id"] for r in asset_rows]

            group = DuplicateGroup(
                id=row["id"],
                scan_run_id=row["scan_run_id"],
                kind=self._duplicate_kind_from_string(row["kind"]),
                representative_asset_id=row["representative_asset_id"],
                distance=row["distance"],
                asset_ids=asset_ids,
            )
            groups.append(group)

        return groups

    def _update_scan_status(self, scan_id: str, status: ScanStatus) -> None:
        """更新扫描任务状态"""
        now = datetime.now()
        if status == ScanStatus.COMPLETED:
            self.db_manager.execute(
                "UPDATE scan_run SET status = ?, completed_at = ? WHERE id = ?",
                (status.value, now.isoformat(), scan_id),
            )
        else:
            self.db_manager.execute(
                "UPDATE scan_run SET status = ? WHERE id = ?",
                (status.value, scan_id),
            )

    def _add_scan_error(self, scan_id: str, error: str) -> None:
        """添加扫描错误"""
        row = self.db_manager.fetchone(
            "SELECT error_messages, error_count FROM scan_run WHERE id = ?",
            (scan_id,),
        )
        if row:
            errors = json.loads(row["error_messages"]) if row["error_messages"] else []
            errors.append(error)
            self.db_manager.execute(
                "UPDATE scan_run SET error_messages = ?, error_count = ? WHERE id = ?",
                (json.dumps(errors), len(errors), scan_id),
            )

    def _save_asset(self, asset: Asset) -> None:
        """保存资产到数据库"""
        asset_id = str(uuid.uuid4())
        asset.id = asset_id

        self.db_manager.execute(
            """
            INSERT INTO asset (id, scan_run_id, path, filename, sha256, phash, size, mtime, width, height, thumbnail_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                asset.scan_run_id,
                asset.path,
                asset.filename,
                asset.sha256,
                asset.phash,
                asset.size,
                asset.mtime.isoformat(),
                asset.width,
                asset.height,
                asset.thumbnail_path,
            ),
        )

    def _save_duplicate_group(self, group: DuplicateGroup) -> None:
        """保存重复组到数据库"""
        group_id = str(uuid.uuid4())
        group.id = group_id

        # 保存组
        self.db_manager.execute(
            """
            INSERT INTO duplicate_group (id, scan_run_id, kind, representative_asset_id, distance)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                group_id,
                group.scan_run_id,
                group.kind.value,
                group.representative_asset_id,
                group.distance,
            ),
        )

        # 保存组成员
        for asset_id in group.asset_ids:
            self.db_manager.execute(
                """
                INSERT INTO duplicate_group_asset (group_id, asset_id)
                VALUES (?, ?)
                """,
                (group_id, asset_id),
            )
