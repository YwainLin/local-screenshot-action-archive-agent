"""Agent 编排器单元测试"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from app.agent.orchestrator import AgentOrchestrator
from app.agent.state import (
    AgentPhase,
    AgentState,
    ApprovalDecision,
    ApprovalRequest,
)
from app.storage.database import DatabaseManager
from app.storage.migrations import run_migrations


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_manager(temp_dir):
    """创建数据库管理器"""
    db_path = temp_dir / "test.db"
    manager = DatabaseManager(str(db_path))
    run_migrations(manager)
    yield manager
    manager.close()


@pytest.fixture
def orchestrator(db_manager):
    """创建 Agent 编排器"""
    return AgentOrchestrator(db_manager)


@pytest.fixture
def sample_directory(temp_dir):
    """创建示例目录"""
    img_dir = temp_dir / "screenshots"
    img_dir.mkdir()

    # 创建示例图片
    for i in range(3):
        img = Image.new("RGB", (100, 100), color=["red", "green", "blue"][i])
        img.save(img_dir / f"test_{i}.png", "PNG")

    return img_dir


@pytest.fixture
def initialized_orchestrator(orchestrator, sample_directory):
    """创建已初始化的编排器"""
    # 创建扫描任务
    scan_run = orchestrator.scan_manager.create_scan_run(str(sample_directory))
    # 执行扫描
    orchestrator.scan_manager.start_scan(scan_run.id)
    return orchestrator, scan_run.id


class TestAgentState:
    """Agent 状态测试"""

    def test_create_state(self):
        """测试创建状态"""
        state = AgentState(
            workspace_id="ws-1",
            scan_run_id="scan-1",
        )

        assert state.workspace_id == "ws-1"
        assert state.scan_run_id == "scan-1"
        assert state.current_phase == AgentPhase.INVENTORY
        assert state.asset_ids == []
        assert state.proposal_ids == []

    def test_state_defaults(self):
        """测试状态默认值"""
        state = AgentState(workspace_id="ws-1")

        assert state.approval_decision == ApprovalDecision.PENDING
        assert state.total_files == 0
        assert state.error_message is None


class TestAgentOrchestrator:
    """Agent 编排器测试"""

    def test_create_state(self, orchestrator):
        """测试创建状态"""
        state = orchestrator.create_state("ws-1", "scan-1")

        assert state.workspace_id == "ws-1"
        assert state.scan_run_id == "scan-1"
        assert state.current_phase == AgentPhase.INVENTORY
        assert state.started_at is not None

    def test_run_inventory(self, initialized_orchestrator):
        """测试资产清点"""
        orchestrator, scan_id = initialized_orchestrator
        state = orchestrator.create_state("ws-1", scan_id)

        result = orchestrator.run_inventory(state)

        assert result.success
        assert len(state.asset_ids) == 3
        assert state.total_files == 3
        assert state.current_phase == AgentPhase.DEDUPLICATE

    def test_run_inventory_no_scan_id(self, orchestrator):
        """测试无扫描 ID 的资产清点"""
        state = orchestrator.create_state("ws-1", None)

        result = orchestrator.run_inventory(state)

        assert not result.success
        assert "扫描任务 ID 不存在" in result.error_message

    def test_run_deduplicate(self, initialized_orchestrator):
        """测试去重"""
        orchestrator, scan_id = initialized_orchestrator
        state = orchestrator.create_state("ws-1", scan_id)
        orchestrator.run_inventory(state)

        result = orchestrator.run_deduplicate(state)

        assert result.success
        assert state.current_phase == AgentPhase.OCR_EXTRACT

    def test_run_ocr_extract(self, initialized_orchestrator):
        """测试 OCR 提取"""
        orchestrator, scan_id = initialized_orchestrator
        state = orchestrator.create_state("ws-1", scan_id)
        orchestrator.run_inventory(state)

        result = orchestrator.run_ocr_extract(state)

        assert result.success
        assert state.ocr_completed == 3
        assert state.current_phase == AgentPhase.GRAPH_INDEX

    def test_run_retrieve_and_plan(self, initialized_orchestrator):
        """测试检索和计划生成"""
        orchestrator, scan_id = initialized_orchestrator
        state = orchestrator.create_state("ws-1", scan_id)
        orchestrator.run_inventory(state)
        orchestrator.run_ocr_extract(state)

        result = orchestrator.run_retrieve_and_plan(state)

        assert result.success
        assert len(state.proposal_ids) > 0
        assert state.current_phase == AgentPhase.APPROVAL_INTERRUPT

    def test_run_full_pipeline(self, initialized_orchestrator):
        """测试完整流程"""
        orchestrator, scan_id = initialized_orchestrator
        state = orchestrator.create_state("ws-1", scan_id)

        final_state = orchestrator.run_full_pipeline(state)

        # 流程应该在审批中断阶段停止
        assert final_state.current_phase in [
            AgentPhase.APPROVAL_INTERRUPT,
            AgentPhase.COMPLETED,
        ]
        assert len(final_state.proposal_ids) > 0

    def test_process_approval_approve(self, initialized_orchestrator):
        """测试批准审批"""
        orchestrator, scan_id = initialized_orchestrator
        state = orchestrator.create_state("ws-1", scan_id)
        orchestrator.run_full_pipeline(state)

        if state.pending_proposal_ids:
            request = ApprovalRequest(
                proposal_id=state.pending_proposal_ids[0],
                decision=ApprovalDecision.APPROVE,
            )
            response = orchestrator.process_approval(state, request)

            assert response.applied
            assert request.proposal_id not in state.pending_proposal_ids

    def test_process_approval_reject(self, initialized_orchestrator):
        """测试拒绝审批"""
        orchestrator, scan_id = initialized_orchestrator
        state = orchestrator.create_state("ws-1", scan_id)
        orchestrator.run_full_pipeline(state)

        if state.pending_proposal_ids:
            request = ApprovalRequest(
                proposal_id=state.pending_proposal_ids[0],
                decision=ApprovalDecision.REJECT,
                reason="不需要",
            )
            response = orchestrator.process_approval(state, request)

            assert response.applied
            assert request.proposal_id not in state.pending_proposal_ids
