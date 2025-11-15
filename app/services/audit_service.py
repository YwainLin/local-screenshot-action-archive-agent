from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..storage.models import AuditEvent, AuditEventType


class AuditService:
    """审计日志服务"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_audit_events(
        self,
        limit: int = 100,
        offset: int = 0,
        event_type: Optional[AuditEventType] = None,
    ) -> List[AuditEvent]:
        """获取审计事件列表"""
        query = self.db.query(AuditEvent)

        if event_type:
            query = query.filter(AuditEvent.event_type == event_type)

        return (
            query.order_by(AuditEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_audit_event(self, event_id: str) -> Optional[AuditEvent]:
        """获取单个审计事件"""
        return (
            self.db.query(AuditEvent)
            .filter(AuditEvent.id == event_id)
            .first()
        )

    def get_audit_events_by_proposal(self, proposal_id: str) -> List[AuditEvent]:
        """获取提案相关的审计事件"""
        return (
            self.db.query(AuditEvent)
            .filter(AuditEvent.proposal_id == proposal_id)
            .order_by(AuditEvent.created_at.desc())
            .all()
        )

    def count_audit_events(self, event_type: Optional[AuditEventType] = None) -> int:
        """统计审计事件数量"""
        query = self.db.query(func.count(AuditEvent.id))

        if event_type:
            query = query.filter(AuditEvent.event_type == event_type)

        return query.scalar() or 0

    def get_audit_summary(self) -> Dict[str, int]:
        """获取审计摘要"""
        result = (
            self.db.query(
                AuditEvent.event_type,
                func.count(AuditEvent.id),
            )
            .group_by(AuditEvent.event_type)
            .all()
        )

        summary = {
            "total": 0,
            "proposal_approved": 0,
            "proposal_rejected": 0,
            "file_copied": 0,
            "copy_failed": 0,
        }

        for event_type, count in result:
            summary["total"] += count
            if event_type == AuditEventType.PROPOSAL_APPROVED:
                summary["proposal_approved"] = count
            elif event_type == AuditEventType.PROPOSAL_REJECTED:
                summary["proposal_rejected"] = count
            elif event_type == AuditEventType.FILE_COPIED:
                summary["file_copied"] = count
            elif event_type == AuditEventType.COPY_FAILED:
                summary["copy_failed"] = count

        return summary

    def get_recent_events(self, limit: int = 10) -> List[AuditEvent]:
        """获取最近的审计事件"""
        return (
            self.db.query(AuditEvent)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
            .all()
        )

    def verify_file_integrity(self, event_id: str) -> Dict:
        """验证文件完整性"""
        event = self.get_audit_event(event_id)
        if not event:
            return {"valid": False, "error": "审计事件不存在"}

        if event.event_type != AuditEventType.FILE_COPIED:
            return {"valid": False, "error": "不是文件复制事件"}

        if not event.before_hash or not event.after_hash:
            return {"valid": False, "error": "缺少哈希信息"}

        if not event.target_path:
            return {"valid": False, "error": "缺少目标路径"}

        from pathlib import Path
        import hashlib

        target_path = Path(event.target_path)
        if not target_path.exists():
            return {"valid": False, "error": "目标文件不存在"}

        sha256_hash = hashlib.sha256()
        with open(target_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)

        current_hash = sha256_hash.hexdigest()

        return {
            "valid": current_hash == event.after_hash,
            "expected_hash": event.after_hash,
            "actual_hash": current_hash,
            "source_path": event.source_path,
            "target_path": event.target_path,
        }


def get_audit_service(db: Session) -> AuditService:
    """获取审计日志服务实例"""
    return AuditService(db)
