from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from ..storage.models import (
    AuditEvent,
    AuditEventType,
    ArchiveProposal,
    Asset,
    ProposalStatus,
)


class FileOperator:
    """受控文件操作服务"""

    def __init__(self, db: Session, allowed_directories: Optional[List[Path]] = None) -> None:
        self.db = db
        self.allowed_directories = allowed_directories or []

    def compute_file_hash(self, file_path: Path) -> str:
        """计算文件 SHA-256 哈希"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def is_path_allowed(self, target_path: Path) -> bool:
        """检查目标路径是否在允许的目录内"""
        if not self.allowed_directories:
            return True

        target_resolved = target_path.resolve()
        for allowed_dir in self.allowed_directories:
            try:
                target_resolved.relative_to(allowed_dir.resolve())
                return True
            except ValueError:
                continue

        return False

    def apply_approved_copy(self, proposal_id: str) -> Dict:
        """执行已批准的复制操作"""
        proposal = (
            self.db.query(ArchiveProposal)
            .filter(ArchiveProposal.id == proposal_id)
            .first()
        )

        if not proposal:
            return {"success": False, "error": "归档建议不存在"}

        if proposal.status != ProposalStatus.APPROVED:
            return {"success": False, "error": "归档建议未批准"}

        asset = self.db.query(Asset).filter(Asset.id == proposal.asset_id).first()
        if not asset:
            return {"success": False, "error": "资产不存在"}

        source_path = Path(asset.path)
        if not source_path.exists():
            return {"success": False, "error": f"源文件不存在: {source_path}"}

        if proposal.target_path:
            target_path = Path(proposal.target_path)
        else:
            target_path = Path("workspace/exports") / proposal.target_category / source_path.name

        if not self.is_path_allowed(target_path):
            self._record_audit_event(
                proposal_id=proposal_id,
                event_type=AuditEventType.COPY_FAILED,
                source_path=str(source_path),
                target_path=str(target_path),
                details="目标路径不在允许的目录内",
            )
            return {"success": False, "error": "目标路径不在允许的目录内"}

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if target_path.exists():
                target_path = target_path.with_stem(
                    f"{target_path.stem}_{uuid4().hex[:8]}"
                )

            before_hash = self.compute_file_hash(source_path)

            shutil.copy2(source_path, target_path)

            after_hash = self.compute_file_hash(target_path)

            if before_hash != after_hash:
                target_path.unlink(missing_ok=True)
                self._record_audit_event(
                    proposal_id=proposal_id,
                    event_type=AuditEventType.COPY_FAILED,
                    source_path=str(source_path),
                    target_path=str(target_path),
                    details="副本哈希不匹配",
                )
                return {"success": False, "error": "副本哈希不匹配"}

            proposal.status = ProposalStatus.APPLIED
            proposal.target_path = str(target_path)
            self.db.commit()

            self._record_audit_event(
                proposal_id=proposal_id,
                event_type=AuditEventType.FILE_COPIED,
                before_hash=before_hash,
                after_hash=after_hash,
                source_path=str(source_path),
                target_path=str(target_path),
            )

            return {
                "success": True,
                "source_path": str(source_path),
                "target_path": str(target_path),
                "before_hash": before_hash,
                "after_hash": after_hash,
            }

        except Exception as e:
            self._record_audit_event(
                proposal_id=proposal_id,
                event_type=AuditEventType.COPY_FAILED,
                source_path=str(source_path),
                target_path=str(target_path),
                details=str(e),
            )
            return {"success": False, "error": str(e)}

    def apply_all_approved(self) -> Dict[str, int]:
        """执行所有已批准的复制操作"""
        approved = (
            self.db.query(ArchiveProposal)
            .filter(ArchiveProposal.status == ProposalStatus.APPROVED)
            .all()
        )

        results = {"success": 0, "failed": 0}
        for proposal in approved:
            result = self.apply_approved_copy(proposal.id)
            if result["success"]:
                results["success"] += 1
            else:
                results["failed"] += 1

        return results

    def _record_audit_event(
        self,
        proposal_id: str,
        event_type: AuditEventType,
        before_hash: Optional[str] = None,
        after_hash: Optional[str] = None,
        source_path: Optional[str] = None,
        target_path: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """记录审计事件"""
        audit_event = AuditEvent(
            id=str(uuid4()),
            proposal_id=proposal_id,
            event_type=event_type,
            before_hash=before_hash,
            after_hash=after_hash,
            source_path=source_path,
            target_path=target_path,
            details=details,
            created_at=datetime.utcnow(),
        )
        self.db.add(audit_event)
        self.db.commit()


def get_file_operator(
    db: Session,
    allowed_directories: Optional[List[Path]] = None,
) -> FileOperator:
    """获取文件操作服务实例"""
    return FileOperator(db, allowed_directories)
