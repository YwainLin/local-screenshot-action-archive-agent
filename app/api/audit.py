from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..storage.database import DatabaseManager
from ..services.audit_service import AuditService, get_audit_service
from ..services.file_operator import FileOperator, get_file_operator
from ..storage.models import AuditEventType

router = APIRouter(prefix="/api/v1", tags=["audit"])

db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager("workspace/screenshot-index.db")
        db_manager.create_tables()
    return db_manager


class AuditEventResponse(BaseModel):
    event_id: str
    proposal_id: Optional[str]
    event_type: str
    before_hash: Optional[str]
    after_hash: Optional[str]
    source_path: Optional[str]
    target_path: Optional[str]
    details: Optional[str]
    created_at: str


class AuditEventListResponse(BaseModel):
    total: int
    items: List[AuditEventResponse]


class AuditSummaryResponse(BaseModel):
    total: int
    proposal_approved: int
    proposal_rejected: int
    file_copied: int
    copy_failed: int


class IntegrityCheckResponse(BaseModel):
    valid: bool
    expected_hash: Optional[str]
    actual_hash: Optional[str]
    source_path: Optional[str]
    target_path: Optional[str]
    error: Optional[str] = None


class ApplyRequest(BaseModel):
    proposal_id: str


class BatchApplyResponse(BaseModel):
    success: int
    failed: int


@router.get("/audit", response_model=AuditEventListResponse)
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    event_type: Optional[str] = None,
) -> AuditEventListResponse:
    """获取审计日志列表"""
    db = get_db_manager().get_session()
    try:
        audit_service = get_audit_service(db)

        type_enum = None
        if event_type:
            try:
                type_enum = AuditEventType(event_type)
            except ValueError:
                pass

        events = audit_service.get_audit_events(
            limit=limit, offset=offset, event_type=type_enum
        )
        total = audit_service.count_audit_events(event_type=type_enum)

        items = [
            AuditEventResponse(
                event_id=event.id,
                proposal_id=event.proposal_id,
                event_type=event.event_type.value,
                before_hash=event.before_hash,
                after_hash=event.after_hash,
                source_path=event.source_path,
                target_path=event.target_path,
                details=event.details,
                created_at=event.created_at.isoformat(),
            )
            for event in events
        ]

        return AuditEventListResponse(total=total, items=items)
    finally:
        db.close()


@router.get("/audit/{event_id}", response_model=AuditEventResponse)
async def get_audit_event(event_id: str) -> AuditEventResponse:
    """获取单个审计事件"""
    db = get_db_manager().get_session()
    try:
        audit_service = get_audit_service(db)
        event = audit_service.get_audit_event(event_id)
        if not event:
            raise HTTPException(status_code=404, detail="审计事件不存在")

        return AuditEventResponse(
            event_id=event.id,
            proposal_id=event.proposal_id,
            event_type=event.event_type.value,
            before_hash=event.before_hash,
            after_hash=event.after_hash,
            source_path=event.source_path,
            target_path=event.target_path,
            details=event.details,
            created_at=event.created_at.isoformat(),
        )
    finally:
        db.close()


@router.get("/audit/summary", response_model=AuditSummaryResponse)
async def get_audit_summary() -> AuditSummaryResponse:
    """获取审计摘要"""
    db = get_db_manager().get_session()
    try:
        audit_service = get_audit_service(db)
        summary = audit_service.get_audit_summary()

        return AuditSummaryResponse(
            total=summary["total"],
            proposal_approved=summary["proposal_approved"],
            proposal_rejected=summary["proposal_rejected"],
            file_copied=summary["file_copied"],
            copy_failed=summary["copy_failed"],
        )
    finally:
        db.close()


@router.get("/audit/{event_id}/integrity", response_model=IntegrityCheckResponse)
async def check_file_integrity(event_id: str) -> IntegrityCheckResponse:
    """验证文件完整性"""
    db = get_db_manager().get_session()
    try:
        audit_service = get_audit_service(db)
        result = audit_service.verify_file_integrity(event_id)

        return IntegrityCheckResponse(
            valid=result.get("valid", False),
            expected_hash=result.get("expected_hash"),
            actual_hash=result.get("actual_hash"),
            source_path=result.get("source_path"),
            target_path=result.get("target_path"),
            error=result.get("error"),
        )
    finally:
        db.close()


@router.post("/audit/apply", response_model=Dict)
async def apply_approved_copy(request: ApplyRequest) -> Dict:
    """执行已批准的复制操作"""
    db = get_db_manager().get_session()
    try:
        file_operator = get_file_operator(db)
        result = file_operator.apply_approved_copy(request.proposal_id)
        return result
    finally:
        db.close()


@router.post("/audit/apply-all", response_model=BatchApplyResponse)
async def apply_all_approved() -> BatchApplyResponse:
    """执行所有已批准的复制操作"""
    db = get_db_manager().get_session()
    try:
        file_operator = get_file_operator(db)
        results = file_operator.apply_all_approved()
        return BatchApplyResponse(
            success=results["success"],
            failed=results["failed"],
        )
    finally:
        db.close()
