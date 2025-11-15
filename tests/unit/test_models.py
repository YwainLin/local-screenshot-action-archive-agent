"""数据模型单元测试"""

from datetime import datetime

import pytest

from app.storage.models import (
    ArchiveProposal,
    Asset,
    AuditEvent,
    AuditEventType,
    DuplicateGroup,
    DuplicateKind,
    Extraction,
    OcrResult,
    ProposalAction,
    ProposalStatus,
    ScanRun,
    ScanStatus,
    WorkspaceConfig,
)


class TestWorkspaceConfig:
    """工作区配置模型测试"""

    def test_create_config(self):
        """测试创建工作区配置"""
        config = WorkspaceConfig(
            workspace_id="test",
            root_path="/tmp/screenshots",
        )
        assert config.workspace_id == "test"
        assert config.root_path == "/tmp/screenshots"
        assert config.allowed_export_paths == []
        assert config.thumbnail_max_size == 256
        assert config.phash_threshold == 10
        assert config.enable_local_model is False

    def test_config_with_exports(self):
        """测试带导出路径的配置"""
        config = WorkspaceConfig(
            workspace_id="test",
            root_path="/tmp/screenshots",
            allowed_export_paths=["/tmp/exports", "/tmp/backup"],
        )
        assert len(config.allowed_export_paths) == 2


class TestScanRun:
    """扫描任务模型测试"""

    def test_create_scan_run(self):
        """测试创建扫描任务"""
        scan = ScanRun(
            workspace_id="ws-1",
            root_path="/tmp/screenshots",
        )
        assert scan.workspace_id == "ws-1"
        assert scan.status == ScanStatus.PENDING
        assert scan.total_files == 0

    def test_scan_run_with_status(self):
        """测试带状态的扫描任务"""
        scan = ScanRun(
            workspace_id="ws-1",
            root_path="/tmp/screenshots",
            status=ScanStatus.RUNNING,
        )
        assert scan.status == ScanStatus.RUNNING


class TestAsset:
    """图片资产模型测试"""

    def test_create_asset(self):
        """测试创建资产"""
        asset = Asset(
            scan_run_id="scan-1",
            path="/tmp/screenshots/test.png",
            filename="test.png",
            size=1024,
            mtime=datetime.now(),
        )
        assert asset.scan_run_id == "scan-1"
        assert asset.filename == "test.png"
        assert asset.size == 1024


class TestDuplicateGroup:
    """重复组模型测试"""

    def test_create_exact_group(self):
        """测试创建完全重复组"""
        group = DuplicateGroup(
            scan_run_id="scan-1",
            kind=DuplicateKind.EXACT,
            representative_asset_id="asset-1",
            asset_ids=["asset-1", "asset-2"],
        )
        assert group.kind == DuplicateKind.EXACT
        assert len(group.asset_ids) == 2

    def test_create_near_group(self):
        """测试创建近似重复组"""
        group = DuplicateGroup(
            scan_run_id="scan-1",
            kind=DuplicateKind.NEAR,
            representative_asset_id="asset-1",
            distance=5,
        )
        assert group.kind == DuplicateKind.NEAR
        assert group.distance == 5


class TestOcrResult:
    """OCR 结果模型测试"""

    def test_create_ocr_result(self):
        """测试创建 OCR 结果"""
        result = OcrResult(
            asset_id="asset-1",
            engine="paddleocr",
            language="ch",
            text="测试文本",
            confidence=0.95,
        )
        assert result.engine == "paddleocr"
        assert result.text == "测试文本"
        assert result.is_sensitive is False


class TestExtraction:
    """提取实体模型测试"""

    def test_create_extraction(self):
        """测试创建提取实体"""
        ext = Extraction(
            asset_id="asset-1",
            kind="date",
            value="2024-01-01",
            value_masked="2024-01-**",
            evidence_span="截止日期：2024年1月1日",
            confidence=0.8,
        )
        assert ext.kind == "date"
        assert ext.source == "rule"


class TestArchiveProposal:
    """归档建议模型测试"""

    def test_create_proposal(self):
        """测试创建归档建议"""
        proposal = ArchiveProposal(
            asset_id="asset-1",
            action=ProposalAction.COPY_TO_CATEGORY,
            suggested_category="订单与售后",
            confidence=0.73,
            rationale="OCR 中出现订单号模式",
        )
        assert proposal.action == ProposalAction.COPY_TO_CATEGORY
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.requires_approval is True


class TestAuditEvent:
    """审计事件模型测试"""

    def test_create_audit_event(self):
        """测试创建审计事件"""
        event = AuditEvent(
            proposal_id="prop-1",
            event_type=AuditEventType.COPY,
            asset_id="asset-1",
            source_path="/tmp/screenshots/test.png",
            target_path="/tmp/exports/test.png",
            before_hash="abc123",
            after_hash="abc123",
        )
        assert event.event_type == AuditEventType.COPY
        assert event.success is True
