from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..storage.database import DatabaseManager
from ..services.proposal_builder import ProposalBuilder, get_proposal_builder
from ..storage.models import ProposalStatus

router = APIRouter(prefix="/api/v1", tags=["proposals"])

db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager("workspace/screenshot-index.db")
        db_manager.create_tables()
    return db_manager


class ProposalResponse(BaseModel):
    proposal_id: str
    asset_id: str
    action: str
    target_category: str
    rationale: str
    confidence: float
    status: str
    evidence_refs: str
    rejection_reason: Optional[str]


class ProposalListResponse(BaseModel):
    total: int
    items: List[ProposalResponse]


class ProposalSummaryResponse(BaseModel):
    scan_id: str
    pending: int
    approved: int
    rejected: int
    applied: int


class ApproveRequest(BaseModel):
    reason: str = ""


class BatchApproveRequest(BaseModel):
    proposal_ids: Optional[List[str]] = None


@router.post("/proposals/generate", response_model=Dict[str, int])
async def generate_proposals(scan_id: str) -> Dict[str, int]:
    """基于既有索引生成归档建议"""
    db = get_db_manager().get_session()
    try:
        builder = get_proposal_builder(db)
        proposals = builder.build_proposals_for_scan_run(scan_id)

        summary = builder.get_proposal_summary(scan_id)
        return summary
    finally:
        db.close()


@router.get("/proposals", response_model=ProposalListResponse)
async def list_proposals(
    scan_id: str,
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> ProposalListResponse:
    """获取归档建议列表"""
    db = get_db_manager().get_session()
    try:
        from ..storage.models import ArchiveProposal, Asset

        query = (
            db.query(ArchiveProposal)
            .join(Asset)
            .filter(Asset.scan_run_id == scan_id)
        )

        if status:
            try:
                status_enum = ProposalStatus(status)
                query = query.filter(ArchiveProposal.status == status_enum)
            except ValueError:
                pass

        proposals = query.limit(limit).all()

        items = [
            ProposalResponse(
                proposal_id=p.id,
                asset_id=p.asset_id,
                action=p.action.value,
                target_category=p.target_category or "",
                rationale=p.rationale,
                confidence=p.confidence,
                status=p.status.value,
                evidence_refs=p.evidence_refs,
                rejection_reason=p.rejection_reason,
            )
            for p in proposals
        ]

        return ProposalListResponse(total=len(items), items=items)
    finally:
        db.close()


@router.get("/proposals/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(proposal_id: str) -> ProposalResponse:
    """获取单个归档建议"""
    db = get_db_manager().get_session()
    try:
        builder = get_proposal_builder(db)
        proposal = builder.get_proposal(proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="归档建议不存在")

        return ProposalResponse(
            proposal_id=proposal.id,
            asset_id=proposal.asset_id,
            action=proposal.action.value,
            target_category=proposal.target_category or "",
            rationale=proposal.rationale,
            confidence=proposal.confidence,
            status=proposal.status.value,
            evidence_refs=proposal.evidence_refs,
            rejection_reason=proposal.rejection_reason,
        )
    finally:
        db.close()


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalResponse)
async def approve_proposal(
    proposal_id: str,
    request: ApproveRequest = ApproveRequest(),
) -> ProposalResponse:
    """批准单项建议"""
    db = get_db_manager().get_session()
    try:
        builder = get_proposal_builder(db)
        proposal = builder.approve_proposal(proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="归档建议不存在")

        return ProposalResponse(
            proposal_id=proposal.id,
            asset_id=proposal.asset_id,
            action=proposal.action.value,
            target_category=proposal.target_category or "",
            rationale=proposal.rationale,
            confidence=proposal.confidence,
            status=proposal.status.value,
            evidence_refs=proposal.evidence_refs,
            rejection_reason=proposal.rejection_reason,
        )
    finally:
        db.close()


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
async def reject_proposal(
    proposal_id: str,
    request: ApproveRequest = ApproveRequest(),
) -> ProposalResponse:
    """拒绝并记录原因"""
    db = get_db_manager().get_session()
    try:
        builder = get_proposal_builder(db)
        proposal = builder.reject_proposal(proposal_id, request.reason)
        if not proposal:
            raise HTTPException(status_code=404, detail="归档建议不存在")

        return ProposalResponse(
            proposal_id=proposal.id,
            asset_id=proposal.asset_id,
            action=proposal.action.value,
            target_category=proposal.target_category or "",
            rationale=proposal.rationale,
            confidence=proposal.confidence,
            status=proposal.status.value,
            evidence_refs=proposal.evidence_refs,
            rejection_reason=proposal.rejection_reason,
        )
    finally:
        db.close()


@router.post("/proposals/batch-approve", response_model=Dict[str, int])
async def batch_approve(
    request: BatchApproveRequest = BatchApproveRequest(),
) -> Dict[str, int]:
    """批量批准建议"""
    db = get_db_manager().get_session()
    try:
        builder = get_proposal_builder(db)
        if request.proposal_ids:
            count = 0
            for pid in request.proposal_ids:
                proposal = builder.approve_proposal(pid)
                if proposal:
                    count += 1
            return {"approved": count}
        else:
            count = builder.approve_all_pending()
            return {"approved": count}
    finally:
        db.close()


@router.get("/proposals/summary/{scan_id}", response_model=ProposalSummaryResponse)
async def get_proposal_summary(scan_id: str) -> ProposalSummaryResponse:
    """获取归档建议摘要"""
    db = get_db_manager().get_session()
    try:
        builder = get_proposal_builder(db)
        summary = builder.get_proposal_summary(scan_id)

        return ProposalSummaryResponse(
            scan_id=scan_id,
            pending=summary["pending"],
            approved=summary["approved"],
            rejected=summary["rejected"],
            applied=summary["applied"],
        )
    finally:
        db.close()
