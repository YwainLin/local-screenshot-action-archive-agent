from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class AgentState(str, enum.Enum):
    """Agent 状态"""
    IDLE = "idle"
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


@dataclass
class WorkflowState:
    """工作流状态"""
    workspace_id: str
    scan_run_id: str
    asset_ids: List[str] = field(default_factory=list)
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    proposal_ids: List[str] = field(default_factory=list)
    approval_decision: Optional[str] = None
    audit_refs: List[Dict[str, Any]] = field(default_factory=list)
    current_state: AgentState = AgentState.IDLE
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentOrchestrator:
    """Agent 编排器（简化版 LangGraph 状态图）"""

    def __init__(self) -> None:
        self.state_transitions = {
            AgentState.IDLE: AgentState.INVENTORY,
            AgentState.INVENTORY: AgentState.DEDUPLICATE,
            AgentState.DEDUPLICATE: AgentState.OCR_EXTRACT,
            AgentState.OCR_EXTRACT: AgentState.GRAPH_INDEX,
            AgentState.GRAPH_INDEX: AgentState.RETRIEVE_AND_PLAN,
            AgentState.RETRIEVE_AND_PLAN: AgentState.APPROVAL_INTERRUPT,
            AgentState.APPROVAL_INTERRUPT: None,  # 等待用户输入
            AgentState.APPLY_COPY: AgentState.AUDIT,
            AgentState.RECORD_FEEDBACK: AgentState.AUDIT,
            AgentState.AUDIT: AgentState.COMPLETED,
        }
        self.state_handlers = {
            AgentState.INVENTORY: self._handle_inventory,
            AgentState.DEDUPLICATE: self._handle_deduplicate,
            AgentState.OCR_EXTRACT: self._handle_ocr_extract,
            AgentState.GRAPH_INDEX: self._handle_graph_index,
            AgentState.RETRIEVE_AND_PLAN: self._handle_retrieve_and_plan,
            AgentState.APPROVAL_INTERRUPT: self._handle_approval_interrupt,
            AgentState.APPLY_COPY: self._handle_apply_copy,
            AgentState.RECORD_FEEDBACK: self._handle_record_feedback,
            AgentState.AUDIT: self._handle_audit,
        }

    def create_workflow_state(
        self,
        workspace_id: str,
        scan_run_id: str,
    ) -> WorkflowState:
        """创建工作流状态"""
        return WorkflowState(
            workspace_id=workspace_id,
            scan_run_id=scan_run_id,
        )

    async def execute_step(self, state: WorkflowState) -> WorkflowState:
        """执行单个工作流步骤"""
        handler = self.state_handlers.get(state.current_state)
        if handler:
            try:
                state = await handler(state)
                next_state = self.state_transitions.get(state.current_state)
                if next_state is not None:
                    state.current_state = next_state
                elif state.current_state == AgentState.APPROVAL_INTERRUPT:
                    pass  # 等待用户输入
            except Exception as e:
                state.error = str(e)
                state.current_state = AgentState.FAILED

        return state

    async def execute_workflow(self, state: WorkflowState) -> WorkflowState:
        """执行完整工作流直到中断或完成"""
        while state.current_state not in (
            AgentState.COMPLETED,
            AgentState.FAILED,
            AgentState.APPROVAL_INTERRUPT,
        ):
            state = await self.execute_step(state)

        return state

    async def _handle_inventory(self, state: WorkflowState) -> WorkflowState:
        """处理资产清点阶段"""
        state.current_state = AgentState.INVENTORY
        state.metadata["inventory_completed"] = True
        return state

    async def _handle_deduplicate(self, state: WorkflowState) -> WorkflowState:
        """处理重复检测阶段"""
        state.current_state = AgentState.DEDUPLICATE
        state.metadata["deduplication_completed"] = True
        return state

    async def _handle_ocr_extract(self, state: WorkflowState) -> WorkflowState:
        """处理 OCR 提取阶段"""
        state.current_state = AgentState.OCR_EXTRACT
        state.metadata["ocr_completed"] = True
        return state

    async def _handle_graph_index(self, state: WorkflowState) -> WorkflowState:
        """处理图索引阶段"""
        state.current_state = AgentState.GRAPH_INDEX
        state.metadata["graph_index_completed"] = True
        return state

    async def _handle_retrieve_and_plan(self, state: WorkflowState) -> WorkflowState:
        """处理检索与计划生成阶段"""
        state.current_state = AgentState.RETRIEVE_AND_PLAN
        state.metadata["plan_generated"] = True
        return state

    async def _handle_approval_interrupt(self, state: WorkflowState) -> WorkflowState:
        """处理审批中断"""
        state.current_state = AgentState.APPROVAL_INTERRUPT
        state.metadata["awaiting_approval"] = True
        return state

    async def _handle_apply_copy(self, state: WorkflowState) -> WorkflowState:
        """处理复制执行阶段"""
        state.current_state = AgentState.APPLY_COPY
        state.metadata["copy_applied"] = True
        return state

    async def _handle_record_feedback(self, state: WorkflowState) -> WorkflowState:
        """处理反馈记录阶段"""
        state.current_state = AgentState.RECORD_FEEDBACK
        state.metadata["feedback_recorded"] = True
        return state

    async def _handle_audit(self, state: WorkflowState) -> WorkflowState:
        """处理审计记录阶段"""
        state.current_state = AgentState.AUDIT
        state.metadata["audit_recorded"] = True
        return state


def get_orchestrator() -> AgentOrchestrator:
    """获取编排器实例"""
    return AgentOrchestrator()
