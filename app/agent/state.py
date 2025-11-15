"""Agent 状态模型定义"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentPhase(str, Enum):
    """Agent 执行阶段"""
    INVENTORY = "inventory"
    DEDUPLICATE = "deduplicate"
    OCR_EXTRACT = "ocr_extract"
    GRAPH_INDEX = "graph_index"
    RETRIEVE_AND_PLAN = "retrieve_and_plan"
    APPROVAL_INTERRUPT = "approval_interrupt"
    APPLY_COPY = "apply_copy"
    RECORD_FEEDBACK = "record_feedback"
    AUDIT = "audit"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalDecision(str, Enum):
    """审批决定"""
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    PENDING = "pending"


class AgentState(BaseModel):
    """Agent 状态模型

    用于 LangGraph 状态图的状态定义。
    """
    # 工作区信息
    workspace_id: str = Field(..., description="工作区 ID")
    scan_run_id: Optional[str] = Field(None, description="扫描任务 ID")

    # 资产信息
    asset_ids: list[str] = Field(default_factory=list, description="资产 ID 列表")
    processed_asset_ids: list[str] = Field(default_factory=list, description="已处理资产 ID 列表")

    # 证据引用
    evidence_refs: list[dict[str, Any]] = Field(
        default_factory=list, description="证据引用列表"
    )

    # 建议信息
    proposal_ids: list[str] = Field(default_factory=list, description="建议 ID 列表")
    pending_proposal_ids: list[str] = Field(default_factory=list, description="待审批建议 ID 列表")

    # 审批信息
    approval_decision: ApprovalDecision = Field(
        default=ApprovalDecision.PENDING, description="审批决定"
    )
    approval_reason: Optional[str] = Field(None, description="审批理由")
    edited_proposals: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="编辑后的建议"
    )

    # 审计信息
    audit_refs: list[str] = Field(default_factory=list, description="审计记录 ID 列表")

    # 状态信息
    current_phase: AgentPhase = Field(
        default=AgentPhase.INVENTORY, description="当前阶段"
    )
    error_message: Optional[str] = Field(None, description="错误信息")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")

    # 统计信息
    total_files: int = Field(default=0, description="总文件数")
    duplicate_groups: int = Field(default=0, description="重复组数")
    ocr_completed: int = Field(default=0, description="已完成 OCR 数")
    proposals_generated: int = Field(default=0, description="已生成建议数")

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
        }
    )


class NodeResult(BaseModel):
    """节点执行结果"""
    success: bool = Field(..., description="是否成功")
    next_phase: Optional[AgentPhase] = Field(None, description="下一阶段")
    error_message: Optional[str] = Field(None, description="错误信息")
    data: dict[str, Any] = Field(default_factory=dict, description="附加数据")


class ApprovalRequest(BaseModel):
    """审批请求"""
    proposal_id: str = Field(..., description="建议 ID")
    decision: ApprovalDecision = Field(..., description="审批决定")
    reason: Optional[str] = Field(None, description="理由/原因")
    edits: Optional[dict[str, Any]] = Field(None, description="编辑内容")


class ApprovalResponse(BaseModel):
    """审批响应"""
    proposal_id: str = Field(..., description="建议 ID")
    decision: ApprovalDecision = Field(..., description="审批决定")
    applied: bool = Field(default=False, description="是否已应用")
    error_message: Optional[str] = Field(None, description="错误信息")
