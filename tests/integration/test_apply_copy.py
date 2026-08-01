"""FileOperator.apply_approved_copy 集成测试"""

import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.file_operator import FileOperator, get_file_operator
from app.storage.database import DatabaseManager
from app.storage.migrations import run_migrations


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
def sample_file(temp_dir):
    src_dir = temp_dir / "source"
    src_dir.mkdir()
    (src_dir / "test.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return src_dir / "test.png"


class TestApplyApprovedCopy:
    """apply_approved_copy 集成测试"""

    def test_apply_approved_copy_success(self, db_manager, sample_file, temp_dir):
        """测试批准后复制成功"""
        export_dir = temp_dir / "exports"
        export_dir.mkdir()

        scan_id = str(uuid4())
        db_manager.execute(
            "INSERT INTO scan_run (id, root_path, status) VALUES (?, ?, ?)",
            (scan_id, str(temp_dir), "completed"),
        )

        asset_id = str(uuid4())
        db_manager.execute(
            """
            INSERT INTO asset (id, scan_run_id, path, filename, size, mtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (asset_id, scan_id, str(sample_file), "test.png", 100, datetime.now().isoformat()),
        )

        proposal_id = str(uuid4())
        db_manager.execute(
            """
            INSERT INTO archive_proposal (id, asset_id, action, suggested_category, confidence, rationale, requires_approval, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (proposal_id, asset_id, "copy_to_category", "截图", 0.9, "测试", 1, "approved"),
        )

        file_op = FileOperator(db_manager)
        result = file_op.apply_approved_copy(proposal_id, export_base=str(export_dir))

        assert result["success"] is True
        assert "target_path" in result

        target = Path(result["target_path"])
        assert target.exists()

    def test_apply_approved_copy_not_found(self, db_manager):
        """测试建议不存在"""
        file_op = FileOperator(db_manager)
        result = file_op.apply_approved_copy("nonexistent-id")
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_apply_approved_copy_wrong_status(self, db_manager, sample_file, temp_dir):
        """测试非 approved 状态"""
        export_dir = temp_dir / "exports"
        export_dir.mkdir()

        scan_id = str(uuid4())
        db_manager.execute(
            "INSERT INTO scan_run (id, root_path, status) VALUES (?, ?, ?)",
            (scan_id, str(temp_dir), "completed"),
        )

        asset_id = str(uuid4())
        db_manager.execute(
            """
            INSERT INTO asset (id, scan_run_id, path, filename, size, mtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (asset_id, scan_id, str(sample_file), "test.png", 100, datetime.now().isoformat()),
        )

        proposal_id = str(uuid4())
        db_manager.execute(
            """
            INSERT INTO archive_proposal (id, asset_id, action, suggested_category, confidence, rationale, requires_approval, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (proposal_id, asset_id, "copy_to_category", "截图", 0.9, "测试", 1, "pending"),
        )

        file_op = FileOperator(db_manager)
        result = file_op.apply_approved_copy(proposal_id, export_base=str(export_dir))
        assert result["success"] is False
        assert "approved" in result["error"]

    def test_apply_all_approved(self, db_manager, temp_dir):
        """测试批量执行所有已批准复制"""
        export_dir = temp_dir / "exports"
        export_dir.mkdir()

        scan_id = str(uuid4())
        db_manager.execute(
            "INSERT INTO scan_run (id, root_path, status) VALUES (?, ?, ?)",
            (scan_id, str(temp_dir), "completed"),
        )

        for i in range(3):
            asset_id = str(uuid4())
            src = temp_dir / f"file_{i}.txt"
            src.write_text(f"content {i}")
            db_manager.execute(
                """
                INSERT INTO asset (id, scan_run_id, path, filename, size, mtime)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (asset_id, scan_id, str(src), f"file_{i}.txt", 10, datetime.now().isoformat()),
            )

            proposal_id = str(uuid4())
            db_manager.execute(
                """
                INSERT INTO archive_proposal (id, asset_id, action, suggested_category, confidence, rationale, requires_approval, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (proposal_id, asset_id, "copy_to_category", "文档", 0.9, "测试", 1, "approved"),
            )

        file_op = FileOperator(db_manager)
        result = file_op.apply_all_approved(export_base=str(export_dir))

        assert result["success"] == 3
        assert result["failed"] == 0

    def test_get_file_operator_factory(self, db_manager):
        """测试工厂函数"""
        op = get_file_operator(db_manager)
        assert isinstance(op, FileOperator)
