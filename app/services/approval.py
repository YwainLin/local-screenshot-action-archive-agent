"""审批服务"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from app.storage.database import DatabaseManager
from app.storage.models import (
    ArchiveProposal,
    AuditEvent,
    AuditEventType,
    ProposalAction,
    ProposalStatus,
)

logger = logging.getLogger(__name__)


class ApprovalService:
    """审批服务"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_proposal(self, proposal_id: str) -> Optional[ArchiveProposal]:
        """获取归档建议

        Args:
            proposal_id: 建议 ID

        Returns:
            ArchiveProposal 模型，不存在则返回 None
        """
        row = self.db_manager.fetchone(
            "SELECT * FROM archive_proposal WHERE id = ?",
            (proposal_id,),
        )
        if not row:
            return None

        return ArchiveProposal(
            id=row["id"],
            asset_id=row["asset_id"],
            action=ProposalAction(row["action"]),
            suggested_category=row["suggested_category"],
            target_path=row["target_path"],
            confidence=row["confidence"],
            rationale=row["rationale"],
            requires_approval=bool(row["requires_approval"]),
            status=ProposalStatus(row["status"]),
            rejection_reason=row["rejection_reason"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    def list_proposals(
        self,
        status: Optional[ProposalStatus] = None,
        limit: int = 50,
    ) -> list[ArchiveProposal]:
        """列出归档建议

        Args:
            status: 过滤状态
            limit: 返回数量限制

        Returns:
            ArchiveProposal 列表
        """
        if status:
            rows = self.db_manager.fetchall(
                "SELECT * FROM archive_proposal WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status.value, limit),
            )
        else:
            rows = self.db_manager.fetchall(
                "SELECT * FROM archive_proposal ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )

        return [
            ArchiveProposal(
                id=row["id"],
                asset_id=row["asset_id"],
                action=ProposalAction(row["action"]),
                suggested_category=row["suggested_category"],
                target_path=row["target_path"],
                confidence=row["confidence"],
                rationale=row["rationale"],
                requires_approval=bool(row["requires_approval"]),
                status=ProposalStatus(row["status"]),
                rejection_reason=row["rejection_reason"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
            )
            for row in rows
        ]

    def approve_proposal(
        self,
        proposal_id: str,
        target_path: Optional[str] = None,
    ) -> AuditEvent:
        """批准归档建议

        Args:
            proposal_id: 建议 ID
            target_path: 目标路径（可选）

        Returns:
            AuditEvent
        """
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"建议不存在: {proposal_id}")

        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(f"建议状态不允许批准: {proposal.status}")

        # 更新建议状态
        now = datetime.now()
        self.db_manager.execute(
            """
            UPDATE archive_proposal
            SET status = ?, target_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (ProposalStatus.APPROVED.value, target_path, now.isoformat(), proposal_id),
        )

        # 创建审计事件
        audit_id = str(uuid.uuid4())
        self.db_manager.execute(
            """
            INSERT INTO audit_event (id, proposal_id, event_type, asset_id, source_path, target_path, success)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                proposal_id,
                AuditEventType.PROPOSAL_APPROVED.value,
                proposal.asset_id,
                "",
                target_path,
                1,
            ),
        )

        logger.info(f"建议已批准: {proposal_id}")
        return AuditEvent(
            id=audit_id,
            proposal_id=proposal_id,
            event_type=AuditEventType.PROPOSAL_APPROVED,
            asset_id=proposal.asset_id,
            source_path="",
            target_path=target_path,
        )

    def reject_proposal(
        self,
        proposal_id: str,
        reason: Optional[str] = None,
    ) -> AuditEvent:
        """拒绝归档建议

        Args:
            proposal_id: 建议 ID
            reason: 拒绝理由

        Returns:
            AuditEvent
        """
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"建议不存在: {proposal_id}")

        if proposal.status != ProposalStatus.PENDING:
            raise ValueError(f"建议状态不允许拒绝: {proposal.status}")

        # 更新建议状态
        now = datetime.now()
        self.db_manager.execute(
            """
            UPDATE archive_proposal
            SET status = ?, rejection_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (ProposalStatus.REJECTED.value, reason, now.isoformat(), proposal_id),
        )

        # 创建审计事件
        audit_id = str(uuid.uuid4())
        self.db_manager.execute(
            """
            INSERT INTO audit_event (id, proposal_id, event_type, asset_id, source_path, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                proposal_id,
                AuditEventType.PROPOSAL_REJECTED.value,
                proposal.asset_id,
                "",
                1,
                reason,
            ),
        )

        logger.info(f"建议已拒绝: {proposal_id}, 原因: {reason}")
        return AuditEvent(
            id=audit_id,
            proposal_id=proposal_id,
            event_type=AuditEventType.PROPOSAL_REJECTED,
            asset_id=proposal.asset_id,
            source_path="",
            error_message=reason,
        )

    def batch_approve(
        self,
        proposal_ids: list[str],
        target_path: Optional[str] = None,
    ) -> list[AuditEvent]:
        """批量批准建议

        Args:
            proposal_ids: 建议 ID 列表
            target_path: 目标路径

        Returns:
            AuditEvent 列表
        """
        events = []
        for proposal_id in proposal_ids:
            try:
                event = self.approve_proposal(proposal_id, target_path)
                events.append(event)
            except Exception as e:
                logger.error(f"批量批准失败 {proposal_id}: {e}")

        return events

    def get_pending_proposals(self) -> list[ArchiveProposal]:
        """获取待审批的建议

        Returns:
            ArchiveProposal 列表
        """
        return self.list_proposals(status=ProposalStatus.PENDING)

    def get_proposal_stats(self) -> dict:
        """获取建议统计

        Returns:
            统计信息字典
        """
        rows = self.db_manager.fetchall(
            """
            SELECT status, COUNT(*) as count
            FROM archive_proposal
            GROUP BY status
            """
        )

        stats = {
            "total": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "applied": 0,
        }

        for row in rows:
            status = row["status"]
            count = row["count"]
            stats["total"] += count
            if status in stats:
                stats[status] = count

        return stats
