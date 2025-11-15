"""审批服务单元测试"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.services.approval import ApprovalService
from app.storage.database import DatabaseManager
from app.storage.migrations import run_migrations
from app.storage.models import ProposalStatus


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
def approval_service(db_manager):
    """创建审批服务"""
    return ApprovalService(db_manager)


@pytest.fixture
def populated_db(db_manager):
    """填充测试数据"""
    # 插入扫描任务
    db_manager.execute(
        "INSERT INTO scan_run (id, root_path, status) VALUES (?, ?, ?)",
        ("scan-1", "/tmp/screenshots", "completed"),
    )

    # 插入资产
    db_manager.execute(
        """
        INSERT INTO asset (id, scan_run_id, path, filename, size, mtime)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("asset-1", "scan-1", "/tmp/screenshots/test.png", "test.png", 1024, datetime.now().isoformat()),
    )

    # 插入建议
    proposals = [
        ("prop-1", "asset-1", "copy_to_category", "订单与售后", 0.8, "测试建议1", 1, "pending"),
        ("prop-2", "asset-1", "copy_to_category", "日期相关", 0.7, "测试建议2", 1, "pending"),
        ("prop-3", "asset-1", "keep", None, 0.5, "测试建议3", 0, "approved"),
    ]
    for prop in proposals:
        db_manager.execute(
            """
            INSERT INTO archive_proposal (id, asset_id, action, suggested_category, confidence, rationale, requires_approval, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            prop,
        )

    return db_manager


class TestApprovalService:
    """审批服务测试"""

    def test_get_proposal(self, approval_service, populated_db):
        """测试获取建议"""
        proposal = approval_service.get_proposal("prop-1")

        assert proposal is not None
        assert proposal.id == "prop-1"
        assert proposal.status == ProposalStatus.PENDING

    def test_get_proposal_not_found(self, approval_service, populated_db):
        """测试获取不存在的建议"""
        proposal = approval_service.get_proposal("nonexistent")

        assert proposal is None

    def test_list_proposals(self, approval_service, populated_db):
        """测试列出建议"""
        proposals = approval_service.list_proposals()

        assert len(proposals) == 3

    def test_list_proposals_by_status(self, approval_service, populated_db):
        """test 按状态列出建议"""
        proposals = approval_service.list_proposals(status=ProposalStatus.PENDING)

        assert len(proposals) == 2
        assert all(p.status == ProposalStatus.PENDING for p in proposals)

    def test_approve_proposal(self, approval_service, populated_db):
        """测试批准建议"""
        event = approval_service.approve_proposal("prop-1", "/tmp/target")

        assert event is not None
        assert event.proposal_id == "prop-1"

        # 验证状态已更新
        proposal = approval_service.get_proposal("prop-1")
        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.target_path == "/tmp/target"

    def test_approve_proposal_not_found(self, approval_service, populated_db):
        """测试批准不存在的建议"""
        with pytest.raises(ValueError, match="建议不存在"):
            approval_service.approve_proposal("nonexistent")

    def test_approve_proposal_wrong_status(self, approval_service, populated_db):
        """test 批准状态错误的建议"""
        with pytest.raises(ValueError, match="建议状态不允许批准"):
            approval_service.approve_proposal("prop-3")

    def test_reject_proposal(self, approval_service, populated_db):
        """测试拒绝建议"""
        event = approval_service.reject_proposal("prop-1", "不需要")

        assert event is not None
        assert event.proposal_id == "prop-1"

        # 验证状态已更新
        proposal = approval_service.get_proposal("prop-1")
        assert proposal.status == ProposalStatus.REJECTED
        assert proposal.rejection_reason == "不需要"

    def test_batch_approve(self, approval_service, populated_db):
        """测试批量批准"""
        events = approval_service.batch_approve(["prop-1", "prop-2"])

        assert len(events) == 2

        # 验证状态已更新
        prop1 = approval_service.get_proposal("prop-1")
        prop2 = approval_service.get_proposal("prop-2")
        assert prop1.status == ProposalStatus.APPROVED
        assert prop2.status == ProposalStatus.APPROVED

    def test_get_pending_proposals(self, approval_service, populated_db):
        """测试获取待审批建议"""
        pending = approval_service.get_pending_proposals()

        assert len(pending) == 2
        assert all(p.status == ProposalStatus.PENDING for p in pending)

    def test_get_proposal_stats(self, approval_service, populated_db):
        """test 获取建议统计"""
        stats = approval_service.get_proposal_stats()

        assert stats["total"] == 3
        assert stats["pending"] == 2
        assert stats["approved"] == 1
