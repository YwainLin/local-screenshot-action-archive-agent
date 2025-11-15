"""Agent 编排服务"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from app.agent.state import (
    AgentPhase,
    AgentState,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponse,
    NodeResult,
)
from app.services.deduplication import DeduplicationService
from app.services.extractor import ExtractorService
from app.services.fingerprint import FingerprintService
from app.services.ocr import OcrService
from app.services.scan_manager import ScanManager
from app.services.search import SearchService
from app.storage.database import DatabaseManager
from app.storage.models import (
    ArchiveProposal,
    Extraction,
    OcrResult,
    ProposalAction,
    ProposalStatus,
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Agent 编排器

    负责协调各个服务完成截图整理流程。
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.scan_manager = ScanManager(db_manager)
        self.fingerprint = FingerprintService()
        self.deduplication = DeduplicationService(self.fingerprint)
        self.ocr_service = OcrService()
        self.extractor = ExtractorService()
        self.search_service = SearchService(db_manager)

    def create_state(self, workspace_id: str, scan_run_id: str) -> AgentState:
        """创建初始 Agent 状态

        Args:
            workspace_id: 工作区 ID
            scan_run_id: 扫描任务 ID

        Returns:
            初始 AgentState
        """
        return AgentState(
            workspace_id=workspace_id,
            scan_run_id=scan_run_id,
            current_phase=AgentPhase.INVENTORY,
            started_at=datetime.now(),
        )

    def run_inventory(self, state: AgentState) -> NodeResult:
        """执行资产清点阶段

        Args:
            state: 当前 Agent 状态

        Returns:
            NodeResult
        """
        try:
            if not state.scan_run_id:
                return NodeResult(
                    success=False,
                    error_message="扫描任务 ID 不存在",
                )

            # 获取扫描任务的资产
            assets = self.scan_manager.get_assets_by_scan(state.scan_run_id)
            asset_ids = [a.id for a in assets if a.id]

            # 更新状态
            state.asset_ids = asset_ids
            state.total_files = len(asset_ids)
            state.current_phase = AgentPhase.DEDUPLICATE

            logger.info(f"资产清点完成: {len(asset_ids)} 个文件")
            return NodeResult(
                success=True,
                next_phase=AgentPhase.DEDUPLICATE,
                data={"asset_count": len(asset_ids)},
            )

        except Exception as e:
            logger.error(f"资产清点失败: {e}")
            return NodeResult(
                success=False,
                error_message=str(e),
            )

    def run_deduplicate(self, state: AgentState) -> NodeResult:
        """执行去重阶段

        Args:
            state: 当前 Agent 状态

        Returns:
            NodeResult
        """
        try:
            if not state.scan_run_id:
                return NodeResult(
                    success=False,
                    error_message="扫描任务 ID 不存在",
                )

            # 获取重复组
            groups = self.scan_manager.get_duplicate_groups(state.scan_run_id)
            state.duplicate_groups = len(groups)
            state.current_phase = AgentPhase.OCR_EXTRACT

            logger.info(f"去重完成: {len(groups)} 个重复组")
            return NodeResult(
                success=True,
                next_phase=AgentPhase.OCR_EXTRACT,
                data={"duplicate_groups": len(groups)},
            )

        except Exception as e:
            logger.error(f"去重失败: {e}")
            return NodeResult(
                success=False,
                error_message=str(e),
            )

    def run_ocr_extract(self, state: AgentState) -> NodeResult:
        """执行 OCR 和实体提取阶段

        Args:
            state: 当前 Agent 状态

        Returns:
            NodeResult
        """
        try:
            if not state.scan_run_id:
                return NodeResult(
                    success=False,
                    error_message="扫描任务 ID 不存在",
                )

            # 获取资产
            assets = self.scan_manager.get_assets_by_scan(state.scan_run_id)
            ocr_completed = 0

            for asset in assets:
                if not asset.id or not asset.path:
                    continue

                try:
                    # 执行 OCR
                    ocr_result = self.ocr_service.run_ocr(asset.path, asset.id)

                    # 保存 OCR 结果
                    ocr_id = str(uuid.uuid4())
                    ocr_result.id = ocr_id
                    self._save_ocr_result(ocr_result)

                    # 提取实体
                    extractions = self.extractor.extract_from_ocr_result(ocr_result)
                    for ext in extractions:
                        ext_id = str(uuid.uuid4())
                        ext.id = ext_id
                        self._save_extraction(ext)

                    # 添加到已处理列表
                    if asset.id not in state.processed_asset_ids:
                        state.processed_asset_ids.append(asset.id)

                    ocr_completed += 1

                except Exception as e:
                    logger.warning(f"OCR 失败 {asset.path}: {e}")
                    continue

            state.ocr_completed = ocr_completed
            state.current_phase = AgentPhase.GRAPH_INDEX

            logger.info(f"OCR 提取完成: {ocr_completed}/{len(assets)}")
            return NodeResult(
                success=True,
                next_phase=AgentPhase.GRAPH_INDEX,
                data={"ocr_completed": ocr_completed},
            )

        except Exception as e:
            logger.error(f"OCR 提取失败: {e}")
            return NodeResult(
                success=False,
                error_message=str(e),
            )

    def run_graph_index(self, state: AgentState) -> NodeResult:
        """执行图索引阶段（Neo4j）

        Args:
            state: 当前 Agent 状态

        Returns:
            NodeResult
        """
        # MVP 阶段跳过 Neo4j，直接进入计划生成
        state.current_phase = AgentPhase.RETRIEVE_AND_PLAN
        logger.info("图索引阶段跳过（MVP）")
        return NodeResult(
            success=True,
            next_phase=AgentPhase.RETRIEVE_AND_PLAN,
        )

    def run_retrieve_and_plan(self, state: AgentState) -> NodeResult:
        """执行检索和计划生成阶段

        Args:
            state: 当前 Agent 状态

        Returns:
            NodeResult
        """
        try:
            if not state.scan_run_id:
                return NodeResult(
                    success=False,
                    error_message="扫描任务 ID 不存在",
                )

            # 生成归档建议
            proposals = self._generate_proposals(state)
            proposal_ids = []

            for proposal in proposals:
                proposal_id = str(uuid.uuid4())
                proposal.id = proposal_id
                self._save_proposal(proposal)
                proposal_ids.append(proposal_id)

            state.proposal_ids = proposal_ids
            state.pending_proposal_ids = proposal_ids.copy()
            state.proposals_generated = len(proposals)
            state.current_phase = AgentPhase.APPROVAL_INTERRUPT

            logger.info(f"计划生成完成: {len(proposals)} 个建议")
            return NodeResult(
                success=True,
                next_phase=AgentPhase.APPROVAL_INTERRUPT,
                data={"proposals_count": len(proposals)},
            )

        except Exception as e:
            logger.error(f"计划生成失败: {e}")
            return NodeResult(
                success=False,
                error_message=str(e),
            )

    def run_approval_interrupt(self, state: AgentState) -> NodeResult:
        """审批中断阶段

        暂停执行，等待用户审批。

        Args:
            state: 当前 Agent 状态

        Returns:
            NodeResult
        """
        # 检查是否有待审批的建议
        if not state.pending_proposal_ids:
            state.current_phase = AgentPhase.AUDIT
            return NodeResult(
                success=True,
                next_phase=AgentPhase.AUDIT,
            )

        # 等待用户审批
        state.approval_decision = ApprovalDecision.PENDING
        logger.info(f"等待审批: {len(state.pending_proposal_ids)} 个建议")
        return NodeResult(
            success=True,
            next_phase=AgentPhase.APPROVAL_INTERRUPT,
            data={"pending_count": len(state.pending_proposal_ids)},
        )

    def process_approval(self, state: AgentState, request: ApprovalRequest) -> ApprovalResponse:
        """处理审批请求

        Args:
            state: 当前 Agent 状态
            request: 审批请求

        Returns:
            ApprovalResponse
        """
        try:
            if request.proposal_id not in state.pending_proposal_ids:
                return ApprovalResponse(
                    proposal_id=request.proposal_id,
                    decision=request.decision,
                    applied=False,
                    error_message="建议不存在或已处理",
                )

            # 更新建议状态
            if request.decision == ApprovalDecision.APPROVE:
                self._update_proposal_status(request.proposal_id, ProposalStatus.APPROVED)
                state.pending_proposal_ids.remove(request.proposal_id)
                state.edited_proposals[request.proposal_id] = {"decision": "approved"}

            elif request.decision == ApprovalDecision.REJECT:
                self._update_proposal_status(
                    request.proposal_id, ProposalStatus.REJECTED, request.reason
                )
                state.pending_proposal_ids.remove(request.proposal_id)
                state.edited_proposals[request.proposal_id] = {
                    "decision": "rejected",
                    "reason": request.reason,
                }

            elif request.decision == ApprovalDecision.EDIT:
                if request.edits:
                    state.edited_proposals[request.proposal_id] = {
                        "decision": "edited",
                        "edits": request.edits,
                    }

            return ApprovalResponse(
                proposal_id=request.proposal_id,
                decision=request.decision,
                applied=True,
            )

        except Exception as e:
            logger.error(f"处理审批失败: {e}")
            return ApprovalResponse(
                proposal_id=request.proposal_id,
                decision=request.decision,
                applied=False,
                error_message=str(e),
            )

    def run_apply_copy(self, state: AgentState) -> NodeResult:
        """执行复制阶段

        Args:
            state: 当前 Agent 状态

        Returns:
            NodeResult
        """
        # MVP 阶段只记录操作，不实际复制
        state.current_phase = AgentPhase.AUDIT
        logger.info("复制阶段跳过（MVP）")
        return NodeResult(
            success=True,
            next_phase=AgentPhase.AUDIT,
        )

    def run_audit(self, state: AgentState) -> NodeResult:
        """执行审计阶段

        Args:
            state: 当前 Agent 状态

        Returns:
            NodeResult
        """
        state.completed_at = datetime.now()
        state.current_phase = AgentPhase.COMPLETED

        logger.info("审计完成")
        return NodeResult(
            success=True,
            next_phase=AgentPhase.COMPLETED,
        )

    def execute_phase(self, state: AgentState) -> NodeResult:
        """执行当前阶段

        Args:
            state: 当前 Agent 状态

        Returns:
            NodeResult
        """
        phase_handlers = {
            AgentPhase.INVENTORY: self.run_inventory,
            AgentPhase.DEDUPLICATE: self.run_deduplicate,
            AgentPhase.OCR_EXTRACT: self.run_ocr_extract,
            AgentPhase.GRAPH_INDEX: self.run_graph_index,
            AgentPhase.RETRIEVE_AND_PLAN: self.run_retrieve_and_plan,
            AgentPhase.APPROVAL_INTERRUPT: self.run_approval_interrupt,
            AgentPhase.APPLY_COPY: self.run_apply_copy,
            AgentPhase.AUDIT: self.run_audit,
        }

        handler = phase_handlers.get(state.current_phase)
        if not handler:
            return NodeResult(
                success=False,
                error_message=f"未知阶段: {state.current_phase}",
            )

        return handler(state)

    def run_full_pipeline(self, state: AgentState) -> AgentState:
        """运行完整流程

        Args:
            state: 初始 Agent 状态

        Returns:
            最终 AgentState
        """
        max_iterations = 20
        iteration = 0

        while (
            state.current_phase not in [AgentPhase.COMPLETED, AgentPhase.FAILED]
            and iteration < max_iterations
        ):
            result = self.execute_phase(state)

            if not result.success:
                state.current_phase = AgentPhase.FAILED
                state.error_message = result.error_message
                break

            # 如果是审批中断阶段，停止执行等待用户输入
            if state.current_phase == AgentPhase.APPROVAL_INTERRUPT:
                if state.pending_proposal_ids:
                    break

            iteration += 1

        return state

    def _generate_proposals(self, state: AgentState) -> list[ArchiveProposal]:
        """生成归档建议

        Args:
            state: 当前 Agent 状态

        Returns:
            ArchiveProposal 列表
        """
        proposals = []

        for asset_id in state.asset_ids:
            # 获取资产的提取实体
            rows = self.db_manager.fetchall(
                "SELECT * FROM extraction WHERE asset_id = ?",
                (asset_id,),
            )

            if not rows:
                # 没有提取实体，建议保留
                proposal = ArchiveProposal(
                    asset_id=asset_id,
                    action=ProposalAction.KEEP,
                    confidence=0.5,
                    rationale="未提取到关键信息",
                    requires_approval=False,
                )
                proposals.append(proposal)
                continue

            # 分析提取实体，生成建议
            has_date = any(r["kind"] == "date" for r in rows)
            has_amount = any(r["kind"] == "amount" for r in rows)
            has_action = any(r["kind"] == "action_phrase" for r in rows)
            has_url = any(r["kind"] == "url" for r in rows)

            # 根据实体类型决定分类
            if has_amount or has_action:
                category = "订单与售后"
                confidence = 0.8
                rationale = "包含金额或行动词信息"
            elif has_date:
                category = "日期相关"
                confidence = 0.7
                rationale = "包含日期信息"
            elif has_url:
                category = "链接收藏"
                confidence = 0.6
                rationale = "包含链接信息"
            else:
                category = "其他"
                confidence = 0.5
                rationale = "包含其他信息"

            proposal = ArchiveProposal(
                asset_id=asset_id,
                action=ProposalAction.COPY_TO_CATEGORY,
                suggested_category=category,
                confidence=confidence,
                rationale=rationale,
                requires_approval=confidence < 0.7,
            )
            proposals.append(proposal)

        return proposals

    def _save_ocr_result(self, result: OcrResult) -> None:
        """保存 OCR 结果"""
        self.db_manager.execute(
            """
            INSERT INTO ocr_result (id, asset_id, engine, engine_version, language, text, confidence, is_sensitive)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.id,
                result.asset_id,
                result.engine,
                result.engine_version,
                result.language,
                result.text,
                result.confidence,
                1 if result.is_sensitive else 0,
            ),
        )

    def _save_extraction(self, extraction: Extraction) -> None:
        """保存提取实体"""
        self.db_manager.execute(
            """
            INSERT INTO extraction (id, asset_id, ocr_result_id, kind, value, value_masked, evidence_span, confidence, is_sensitive, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                extraction.id,
                extraction.asset_id,
                extraction.ocr_result_id,
                extraction.kind,
                extraction.value,
                extraction.value_masked,
                extraction.evidence_span,
                extraction.confidence,
                1 if extraction.is_sensitive else 0,
                extraction.source,
            ),
        )

    def _save_proposal(self, proposal: ArchiveProposal) -> None:
        """保存归档建议"""
        self.db_manager.execute(
            """
            INSERT INTO archive_proposal (id, asset_id, action, suggested_category, confidence, rationale, requires_approval, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.id,
                proposal.asset_id,
                proposal.action.value,
                proposal.suggested_category,
                proposal.confidence,
                proposal.rationale,
                1 if proposal.requires_approval else 0,
                proposal.status.value,
            ),
        )

    def _update_proposal_status(
        self,
        proposal_id: str,
        status: ProposalStatus,
        reason: Optional[str] = None,
    ) -> None:
        """更新建议状态"""
        self.db_manager.execute(
            "UPDATE archive_proposal SET status = ?, rejection_reason = ? WHERE id = ?",
            (status.value, reason, proposal_id),
        )
