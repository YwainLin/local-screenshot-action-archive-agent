"""文件操作服务"""

import hashlib
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.storage.database import DatabaseManager
from app.storage.models import (
    AuditEvent,
    AuditEventType,
    ProposalStatus,
)

logger = logging.getLogger(__name__)


class FileOperator:
    """文件操作服务

    仅按批准计划复制或导出文件，不删除、不覆盖。
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def compute_file_hash(self, file_path: str) -> str:
        """计算文件 SHA-256 哈希

        Args:
            file_path: 文件路径

        Returns:
            十六进制哈希字符串
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def copy_file(
        self,
        proposal_id: str,
        source_path: str,
        target_dir: str,
    ) -> AuditEvent:
        """复制文件

        Args:
            proposal_id: 建议 ID
            source_path: 源文件路径
            target_dir: 目标目录

        Returns:
            AuditEvent
        """
        source = Path(source_path)
        if not source.exists():
            raise ValueError(f"源文件不存在: {source_path}")

        if not source.is_file():
            raise ValueError(f"源路径不是文件: {source_path}")

        # 查找 proposal 对应的 asset_id
        proposal = self.db_manager.fetchone(
            "SELECT asset_id FROM archive_proposal WHERE id = ?",
            (proposal_id,),
        )
        asset_id = proposal["asset_id"] if proposal else ""

        # 确保目标目录存在
        target_path = Path(target_dir) / source.name
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 检查目标文件是否已存在
        if target_path.exists():
            raise ValueError(f"目标文件已存在: {target_path}")

        # 计算源文件哈希
        before_hash = self.compute_file_hash(source_path)

        try:
            # 复制文件
            shutil.copy2(source_path, target_path)

            # 计算目标文件哈希
            after_hash = self.compute_file_hash(str(target_path))

            # 验证哈希一致
            if before_hash != after_hash:
                # 哈希不一致，删除目标文件
                target_path.unlink()
                raise ValueError("文件复制后哈希不一致")

            # 更新建议状态
            self.db_manager.execute(
                """
                UPDATE archive_proposal
                SET status = ?, target_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (ProposalStatus.APPLIED.value, str(target_path), datetime.now().isoformat(), proposal_id),
            )

            # 创建审计事件
            audit_id = str(uuid.uuid4())
            self.db_manager.execute(
                """
                INSERT INTO audit_event (id, proposal_id, event_type, asset_id, source_path, target_path, before_hash, after_hash, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    proposal_id,
                    AuditEventType.FILE_COPIED.value,
                    asset_id,
                    source_path,
                    str(target_path),
                    before_hash,
                    after_hash,
                    1,
                ),
            )

            logger.info(f"文件复制成功: {source_path} -> {target_path}")

            return AuditEvent(
                id=audit_id,
                proposal_id=proposal_id,
                event_type=AuditEventType.FILE_COPIED,
                asset_id=asset_id,
                source_path=source_path,
                target_path=str(target_path),
                before_hash=before_hash,
                after_hash=after_hash,
                success=True,
            )

        except Exception as e:
            # 记录失败
            audit_id = str(uuid.uuid4())
            self.db_manager.execute(
                """
                INSERT INTO audit_event (id, proposal_id, event_type, asset_id, source_path, target_path, before_hash, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    proposal_id,
                    AuditEventType.COPY_FAILED.value,
                    asset_id,
                    source_path,
                    str(target_path),
                    before_hash,
                    0,
                    str(e),
                ),
            )

            logger.error(f"文件复制失败: {source_path} -> {target_path}, 错误: {e}")
            raise

    def batch_copy(
        self,
        copies: list[dict],
    ) -> list[AuditEvent]:
        """批量复制文件

        Args:
            copies: 复制任务列表，每项包含 proposal_id, source_path, target_dir

        Returns:
            AuditEvent 列表
        """
        events = []
        for copy_task in copies:
            try:
                event = self.copy_file(
                    proposal_id=copy_task["proposal_id"],
                    source_path=copy_task["source_path"],
                    target_dir=copy_task["target_dir"],
                )
                events.append(event)
            except Exception as e:
                logger.error(f"批量复制失败: {copy_task}, 错误: {e}")

        return events

    def get_audit_events(
        self,
        proposal_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """获取审计事件

        Args:
            proposal_id: 建议 ID（可选）
            limit: 返回数量限制

        Returns:
            AuditEvent 列表
        """
        if proposal_id:
            rows = self.db_manager.fetchall(
                """
                SELECT * FROM audit_event
                WHERE proposal_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (proposal_id, limit),
            )
        else:
            rows = self.db_manager.fetchall(
                """
                SELECT * FROM audit_event
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

        return [
            AuditEvent(
                id=row["id"],
                proposal_id=row["proposal_id"],
                event_type=AuditEventType(row["event_type"]),
                asset_id=row["asset_id"],
                source_path=row["source_path"],
                target_path=row["target_path"],
                before_hash=row["before_hash"],
                after_hash=row["after_hash"],
                success=bool(row["success"]),
                error_message=row["error_message"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            )
            for row in rows
        ]

    def verify_file_integrity(self, file_path: str, expected_hash: str) -> bool:
        """验证文件完整性

        Args:
            file_path: 文件路径
            expected_hash: 期望的哈希值

        Returns:
            是否一致
        """
        try:
            actual_hash = self.compute_file_hash(file_path)
            return actual_hash == expected_hash
        except Exception as e:
            logger.error(f"验证文件完整性失败: {file_path}, 错误: {e}")
            return False
