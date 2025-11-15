"""文件操作服务单元测试"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.services.file_operator import FileOperator
from app.storage.database import DatabaseManager
from app.storage.migrations import run_migrations
from app.storage.models import AuditEventType


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
def file_operator(db_manager):
    """创建文件操作服务"""
    return FileOperator(db_manager)


@pytest.fixture
def sample_files(temp_dir):
    """创建示例文件"""
    # 源目录
    src_dir = temp_dir / "source"
    src_dir.mkdir()

    # 创建测试文件
    (src_dir / "test1.txt").write_text("test content 1")
    (src_dir / "test2.txt").write_text("test content 2")
    (src_dir / "test3.bin").write_bytes(b"\x00\x01\x02\x03")

    return src_dir


@pytest.fixture
def target_dir(temp_dir):
    """创建目标目录"""
    target = temp_dir / "target"
    target.mkdir()
    return target


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
    db_manager.execute(
        """
        INSERT INTO archive_proposal (id, asset_id, action, suggested_category, confidence, rationale, requires_approval, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("prop-1", "asset-1", "copy_to_category", "测试", 0.8, "测试", 1, "approved"),
    )

    return db_manager


class TestFileOperator:
    """文件操作服务测试"""

    def test_compute_file_hash(self, file_operator, sample_files):
        """测试计算文件哈希"""
        file_path = str(sample_files / "test1.txt")
        hash_value = file_operator.compute_file_hash(file_path)

        assert len(hash_value) == 64  # SHA-256
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_copy_file(self, file_operator, sample_files, target_dir, populated_db):
        """测试复制文件"""
        source_path = str(sample_files / "test1.txt")

        event = file_operator.copy_file("prop-1", source_path, str(target_dir))

        assert event.success
        assert event.event_type == AuditEventType.FILE_COPIED
        assert event.before_hash == event.after_hash

        # 验证文件已复制
        target_file = target_dir / "test1.txt"
        assert target_file.exists()
        assert target_file.read_text() == "test content 1"

    def test_copy_file_nonexistent(self, file_operator, target_dir, populated_db):
        """test 复制不存在的文件"""
        with pytest.raises(ValueError, match="源文件不存在"):
            file_operator.copy_file("prop-1", "/nonexistent/file.txt", str(target_dir))

    def test_copy_file_target_exists(self, file_operator, sample_files, target_dir, populated_db):
        """测试目标文件已存在"""
        source_path = str(sample_files / "test1.txt")
        (target_dir / "test1.txt").write_text("existing content")

        with pytest.raises(ValueError, match="目标文件已存在"):
            file_operator.copy_file("prop-1", source_path, str(target_dir))

    def test_batch_copy(self, file_operator, sample_files, target_dir, populated_db):
        """测试批量复制"""
        copies = [
            {
                "proposal_id": "prop-1",
                "source_path": str(sample_files / "test1.txt"),
                "target_dir": str(target_dir),
            },
        ]

        events = file_operator.batch_copy(copies)

        assert len(events) == 1
        assert events[0].success

    def test_get_audit_events(self, file_operator, sample_files, target_dir, populated_db):
        """测试获取审计事件"""
        # 先复制一个文件
        source_path = str(sample_files / "test1.txt")
        file_operator.copy_file("prop-1", source_path, str(target_dir))

        events = file_operator.get_audit_events()

        assert len(events) == 1
        assert events[0].event_type == AuditEventType.FILE_COPIED

    def test_get_audit_events_by_proposal(self, file_operator, sample_files, target_dir, populated_db):
        """测试按建议 ID 获取审计事件"""
        source_path = str(sample_files / "test1.txt")
        file_operator.copy_file("prop-1", source_path, str(target_dir))

        events = file_operator.get_audit_events(proposal_id="prop-1")

        assert len(events) == 1
        assert events[0].proposal_id == "prop-1"

    def test_verify_file_integrity(self, file_operator, sample_files):
        """测试验证文件完整性"""
        file_path = str(sample_files / "test1.txt")
        hash_value = file_operator.compute_file_hash(file_path)

        assert file_operator.verify_file_integrity(file_path, hash_value)
        assert not file_operator.verify_file_integrity(file_path, "wrong_hash")

    def test_copy_preserves_hash(self, file_operator, sample_files, target_dir, populated_db):
        """测试复制后哈希一致"""
        source_path = str(sample_files / "test1.txt")
        event = file_operator.copy_file("prop-1", source_path, str(target_dir))

        assert event.before_hash == event.after_hash

        # 验证目标文件哈希
        target_path = str(target_dir / "test1.txt")
        target_hash = file_operator.compute_file_hash(target_path)
        assert target_hash == event.after_hash
