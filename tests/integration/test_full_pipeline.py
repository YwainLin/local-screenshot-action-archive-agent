"""端到端集成测试：完整流程"""

import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.scanner import ScannerService
from app.services.fingerprint import FingerprintService
from app.services.deduplication import DeduplicationService
from app.services.ocr import OcrService
from app.services.extractor import ExtractorService
from app.services.approval import ApprovalService
from app.services.file_operator import FileOperator
from app.services.search import SearchService
from app.storage.database import DatabaseManager
from app.storage.migrations import run_migrations
from app.storage.models import Asset, DuplicateKind, ProposalStatus


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_manager(temp_dir):
    db_path = temp_dir / "test.db"
    manager = DatabaseManager(str(db_path))
    run_migrations(manager)
    yield manager
    manager.close()


@pytest.fixture
def sample_screenshots(temp_dir):
    src_dir = temp_dir / "screenshots"
    src_dir.mkdir()

    from PIL import Image

    img1 = Image.new("RGB", (100, 100), color="red")
    img1.save(src_dir / "screenshot_001.png")

    img2 = Image.new("RGB", (100, 100), color="blue")
    img2.save(src_dir / "screenshot_002.png")

    img3 = Image.new("RGB", (100, 100), color="red")
    img3.save(src_dir / "screenshot_003.png")

    return src_dir


@pytest.fixture
def export_dir(temp_dir):
    exports = temp_dir / "exports"
    exports.mkdir()
    return exports


class TestFullPipeline:
    """完整流程集成测试"""

    def test_scan_fingerprint_dedup(self, db_manager, sample_screenshots):
        """测试扫描 → 指纹 → 去重流程"""
        scan_id = str(uuid4())
        db_manager.execute(
            "INSERT INTO scan_run (id, root_path, status) VALUES (?, ?, ?)",
            (scan_id, str(sample_screenshots), "running"),
        )

        scanner = ScannerService()
        raw_assets = scanner.list_assets(str(sample_screenshots), scan_id)
        assert len(raw_assets) == 3

        fp_service = FingerprintService()
        asset_objects = []
        for raw in raw_assets:
            asset_id = str(uuid4())
            file_path = Path(raw.path)
            sha256 = fp_service.compute_sha256(file_path)
            phash = fp_service.compute_phash(file_path)

            db_manager.execute(
                """
                INSERT INTO asset (id, scan_run_id, path, filename, size, mtime, sha256, phash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (asset_id, scan_id, raw.path, raw.filename, raw.size,
                 raw.mtime.isoformat() if raw.mtime else datetime.now().isoformat(),
                 sha256, str(phash) if phash else None),
            )

            asset_objects.append(Asset(
                id=asset_id,
                scan_run_id=scan_id,
                path=raw.path,
                filename=raw.filename,
                size=raw.size,
                sha256=sha256,
                phash=str(phash) if phash else None,
            ))

        dedup = DeduplicationService(db_manager)
        exact_groups = dedup.find_exact_duplicates(asset_objects)
        assert len(exact_groups) >= 1

        db_manager.execute(
            "UPDATE scan_run SET status = ?, completed_at = ? WHERE id = ?",
            ("completed", datetime.now().isoformat(), scan_id),
        )

    def test_ocr_extract(self, db_manager, sample_screenshots):
        """测试 OCR → 提取流程"""
        scan_id = str(uuid4())
        db_manager.execute(
            "INSERT INTO scan_run (id, root_path, status) VALUES (?, ?, ?)",
            (scan_id, str(sample_screenshots), "completed"),
        )

        asset_id = str(uuid4())
        db_manager.execute(
            """
            INSERT INTO asset (id, scan_run_id, path, filename, size, mtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (asset_id, scan_id, str(sample_screenshots / "screenshot_001.png"),
             "screenshot_001.png", 1024, datetime.now().isoformat()),
        )

        ocr_service = OcrService()
        ocr_result = ocr_service.run_ocr(
            str(sample_screenshots / "screenshot_001.png"), asset_id
        )
        assert ocr_result.text is not None

        db_manager.execute(
            """
            INSERT INTO ocr_result (id, asset_id, engine, language, text, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), asset_id, ocr_result.engine, ocr_result.language,
             ocr_result.text or "测试文本 2024-01-15 订单号12345", ocr_result.confidence or 0.85),
        )

        extractor = ExtractorService()
        extractions = extractor.extract_from_text("测试文本 2024-01-15 订单号12345", asset_id)
        assert len(extractions) > 0

        for ext in extractions:
            db_manager.execute(
                """
                INSERT INTO extraction (id, asset_id, kind, value, value_masked, evidence_span, confidence, is_sensitive)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), asset_id, ext.kind, ext.value, ext.value_masked,
                 ext.evidence_span, ext.confidence, ext.is_sensitive),
            )

    def test_proposal_approval_copy(self, db_manager, sample_screenshots, export_dir):
        """测试建议 → 审批 → 复制流程"""
        scan_id = str(uuid4())
        db_manager.execute(
            "INSERT INTO scan_run (id, root_path, status) VALUES (?, ?, ?)",
            (scan_id, str(sample_screenshots), "completed"),
        )

        asset_id = str(uuid4())
        src_path = str(sample_screenshots / "screenshot_001.png")
        db_manager.execute(
            """
            INSERT INTO asset (id, scan_run_id, path, filename, size, mtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (asset_id, scan_id, src_path, "screenshot_001.png", 1024, datetime.now().isoformat()),
        )

        proposal_id = str(uuid4())
        db_manager.execute(
            """
            INSERT INTO archive_proposal (id, asset_id, action, suggested_category, confidence, rationale, requires_approval, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (proposal_id, asset_id, "copy_to_category", "测试分类", 0.9, "测试理由", 1, "pending"),
        )

        approval = ApprovalService(db_manager)
        event = approval.approve_proposal(proposal_id)
        assert event is not None

        proposal = db_manager.fetchone(
            "SELECT status FROM archive_proposal WHERE id = ?",
            (proposal_id,),
        )
        assert proposal["status"] == ProposalStatus.APPROVED.value

        file_op = FileOperator(db_manager)
        copy_event = file_op.copy_file(proposal_id, src_path, str(export_dir))
        assert copy_event.success
        assert copy_event.before_hash == copy_event.after_hash

        target_file = export_dir / "screenshot_001.png"
        assert target_file.exists()

        events = file_op.get_audit_events(proposal_id=proposal_id)
        copy_events = [e for e in events if e.event_type.value == "file_copied"]
        assert len(copy_events) == 1
        assert copy_events[0].event_type.value == "file_copied"

    def test_full_e2e_pipeline(self, db_manager, sample_screenshots, export_dir):
        """端到端完整流程测试"""
        scan_id = str(uuid4())
        db_manager.execute(
            "INSERT INTO scan_run (id, root_path, status) VALUES (?, ?, ?)",
            (scan_id, str(sample_screenshots), "running"),
        )

        scanner = ScannerService()
        raw_assets = scanner.list_assets(str(sample_screenshots), scan_id)
        assert len(raw_assets) == 3

        fp_service = FingerprintService()
        saved_asset_ids = []
        for raw in raw_assets:
            asset_id = str(uuid4())
            saved_asset_ids.append(asset_id)
            file_path = Path(raw.path)
            sha256 = fp_service.compute_sha256(file_path)
            phash = fp_service.compute_phash(file_path)
            db_manager.execute(
                """
                INSERT INTO asset (id, scan_run_id, path, filename, size, mtime, sha256, phash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (asset_id, scan_id, raw.path, raw.filename, raw.size,
                 raw.mtime.isoformat() if raw.mtime else datetime.now().isoformat(),
                 sha256, str(phash) if phash else None),
            )

        ocr_service = OcrService()
        for aid in saved_asset_ids:
            row = db_manager.fetchone("SELECT path FROM asset WHERE id = ?", (aid,))
            ocr_result = ocr_service.run_ocr(row["path"], aid)
            db_manager.execute(
                """
                INSERT INTO ocr_result (id, asset_id, engine, language, text, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), aid, "placeholder", "ch",
                 f"测试内容 2024-01-15 订单号{aid[:8]} 验证码1234", 0.85),
            )

        extractor = ExtractorService()
        for aid in saved_asset_ids:
            ocr_row = db_manager.fetchone(
                "SELECT text FROM ocr_result WHERE asset_id = ? LIMIT 1", (aid,)
            )
            if ocr_row:
                extractions = extractor.extract_from_text(ocr_row["text"], aid)
                for ext in extractions:
                    db_manager.execute(
                        """
                        INSERT INTO extraction (id, asset_id, kind, value, value_masked, evidence_span, confidence, is_sensitive)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (str(uuid4()), aid, ext.kind, ext.value, ext.value_masked,
                         ext.evidence_span, ext.confidence, ext.is_sensitive),
                    )

        proposal_ids = []
        for aid in saved_asset_ids:
            proposal_id = str(uuid4())
            proposal_ids.append(proposal_id)
            db_manager.execute(
                """
                INSERT INTO archive_proposal (id, asset_id, action, suggested_category, confidence, rationale, requires_approval, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (proposal_id, aid, "copy_to_category", "测试分类", 0.85, "自动建议", 1, "pending"),
            )

        approval = ApprovalService(db_manager)
        for pid in proposal_ids:
            approval.approve_proposal(pid)

        file_op = FileOperator(db_manager)
        copies = []
        for pid in proposal_ids:
            row = db_manager.fetchone(
                "SELECT a.path FROM asset a JOIN archive_proposal p ON a.id = p.asset_id WHERE p.id = ?",
                (pid,),
            )
            copies.append({
                "proposal_id": pid,
                "source_path": row["path"],
                "target_dir": str(export_dir),
            })

        events = file_op.batch_copy(copies)
        assert len(events) == 3
        assert all(e.success for e in events)

        for pid in proposal_ids:
            proposal = db_manager.fetchone(
                "SELECT status FROM archive_proposal WHERE id = ?", (pid,)
            )
            assert proposal["status"] == ProposalStatus.APPLIED.value

        all_events = file_op.get_audit_events()
        copy_events = [e for e in all_events if e.event_type.value == "file_copied"]
        assert len(copy_events) == 3

        db_manager.execute(
            "UPDATE scan_run SET status = ?, completed_at = ? WHERE id = ?",
            ("completed", datetime.now().isoformat(), scan_id),
        )

        scan = db_manager.fetchone(
            "SELECT status FROM scan_run WHERE id = ?", (scan_id,)
        )
        assert scan["status"] == "completed"
