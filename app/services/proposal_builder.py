from __future__ import annotations

from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from ..storage.models import (
    ArchiveProposal,
    Asset,
    Extraction,
    OcrResult,
    ProposalAction,
    ProposalStatus,
)
from ..services.extractor import RuleExtractor


class ProposalBuilder:
    """归档建议生成器"""

    CATEGORY_RULES = {
        "date": "时间相关",
        "url": "网络资源",
        "amount_candidate": "财务相关",
        "action_phrase": "待办事项",
        "sensitive_candidate": "敏感信息",
    }

    CONFIDENCE_THRESHOLD = 0.6

    def __init__(self, db: Session) -> None:
        self.db = db
        self.extractor = RuleExtractor()

    def build_proposals(
        self,
        asset_id: str,
        ocr_text: str,
        extractions: Optional[List[Dict]] = None,
    ) -> List[ArchiveProposal]:
        """为单个资产生成归档建议"""
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return []

        if not extractions:
            extractions_data = self.extractor.extract_all(ocr_text)
            extractions = [
                {
                    "kind": e.kind,
                    "value_raw": e.value_raw,
                    "value_masked": e.value_masked,
                    "evidence_span": e.evidence_span,
                    "confidence": e.confidence,
                    "is_sensitive": e.is_sensitive,
                }
                for e in extractions_data
            ]

        proposals = []
        for ext in extractions:
            if ext["is_sensitive"]:
                action = ProposalAction.NEEDS_REVIEW
                target_category = "敏感信息需审核"
            elif ext["confidence"] < self.CONFIDENCE_THRESHOLD:
                action = ProposalAction.NEEDS_REVIEW
                target_category = "低置信度需审核"
            elif ext["kind"] in self.CATEGORY_RULES:
                action = ProposalAction.COPY_TO_CATEGORY
                target_category = self.CATEGORY_RULES[ext["kind"]]
            else:
                action = ProposalAction.KEEP_IN_PLACE
                target_category = "未分类"

            proposal = ArchiveProposal(
                id=str(uuid4()),
                asset_id=asset_id,
                action=action,
                target_category=target_category,
                rationale=f"基于 {ext['kind']} 类型提取，置信度 {ext['confidence']:.2f}",
                confidence=ext["confidence"],
                status=ProposalStatus.PENDING,
                evidence_refs=str([ext.get("evidence_span", "")]),
            )
            self.db.add(proposal)
            proposals.append(proposal)

        self.db.commit()
        return proposals

    def build_proposals_for_scan_run(
        self,
        scan_run_id: str,
    ) -> List[ArchiveProposal]:
        """为整个扫描任务生成归档建议"""
        assets = (
            self.db.query(Asset)
            .filter(Asset.scan_run_id == scan_run_id)
            .all()
        )

        all_proposals = []
        for asset in assets:
            ocr_results = (
                self.db.query(OcrResult)
                .filter(OcrResult.asset_id == asset.id)
                .all()
            )

            ocr_text = "\n".join([ocr.text for ocr in ocr_results])

            existing_extractions = (
                self.db.query(Extraction)
                .filter(Extraction.asset_id == asset.id)
                .all()
            )

            if existing_extractions:
                extractions = [
                    {
                        "kind": ext.kind,
                        "value_raw": ext.value_raw,
                        "value_masked": ext.value_masked,
                        "evidence_span": ext.evidence_span,
                        "confidence": ext.confidence,
                        "is_sensitive": ext.is_sensitive,
                    }
                    for ext in existing_extractions
                ]
            else:
                extractions = None

            proposals = self.build_proposals(
                asset_id=asset.id,
                ocr_text=ocr_text,
                extractions=extractions,
            )
            all_proposals.extend(proposals)

        return all_proposals

    def get_proposal(self, proposal_id: str) -> Optional[ArchiveProposal]:
        """获取单个归档建议"""
        return (
            self.db.query(ArchiveProposal)
            .filter(ArchiveProposal.id == proposal_id)
            .first()
        )

    def get_proposals_by_status(
        self,
        status: ProposalStatus,
        limit: int = 100,
    ) -> List[ArchiveProposal]:
        """按状态获取归档建议"""
        return (
            self.db.query(ArchiveProposal)
            .filter(ArchiveProposal.status == status)
            .limit(limit)
            .all()
        )

    def approve_proposal(self, proposal_id: str) -> Optional[ArchiveProposal]:
        """批准归档建议"""
        proposal = self.get_proposal(proposal_id)
        if proposal:
            proposal.status = ProposalStatus.APPROVED
            self.db.commit()
        return proposal

    def reject_proposal(
        self, proposal_id: str, reason: str = ""
    ) -> Optional[ArchiveProposal]:
        """拒绝归档建议"""
        proposal = self.get_proposal(proposal_id)
        if proposal:
            proposal.status = ProposalStatus.REJECTED
            proposal.rejection_reason = reason
            self.db.commit()
        return proposal

    def approve_all_pending(self) -> int:
        """批量批准所有待审批建议"""
        pending = self.get_proposals_by_status(ProposalStatus.PENDING)
        count = 0
        for proposal in pending:
            proposal.status = ProposalStatus.APPROVED
            count += 1
        self.db.commit()
        return count

    def reject_all_pending(self, reason: str = "批量拒绝") -> int:
        """批量拒绝所有待审批建议"""
        pending = self.get_proposals_by_status(ProposalStatus.PENDING)
        count = 0
        for proposal in pending:
            proposal.status = ProposalStatus.REJECTED
            proposal.rejection_reason = reason
            count += 1
        self.db.commit()
        return count

    def get_proposal_summary(self, scan_run_id: str) -> Dict[str, int]:
        """获取归档建议摘要"""
        from sqlalchemy import func

        result = (
            self.db.query(
                ArchiveProposal.status,
                func.count(ArchiveProposal.id),
            )
            .join(Asset)
            .filter(Asset.scan_run_id == scan_run_id)
            .group_by(ArchiveProposal.status)
            .all()
        )

        summary = {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "applied": 0,
        }
        for status, count in result:
            summary[status.value] = count

        return summary


def get_proposal_builder(db: Session) -> ProposalBuilder:
    """获取归档建议生成器实例"""
    return ProposalBuilder(db)
