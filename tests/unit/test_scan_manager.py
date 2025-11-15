"""扫描任务管理单元测试"""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from app.services.scan_manager import ScanManager
from app.storage.database import DatabaseManager
from app.storage.migrations import run_migrations
from app.storage.models import ScanStatus


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
def scan_manager(db_manager):
    """创建扫描管理器"""
    return ScanManager(db_manager)


@pytest.fixture
def sample_directory(temp_dir):
    """创建示例目录"""
    img_dir = temp_dir / "screenshots"
    img_dir.mkdir()

    # 创建示例图片
    for i in range(5):
        img = Image.new("RGB", (100, 100), color=["red", "green", "blue", "yellow", "purple"][i])
        img.save(img_dir / f"test_{i}.png", "PNG")

    # 创建两个完全相同的图片
    img = Image.new("RGB", (100, 100), color="red")
    img.save(img_dir / "duplicate_1.png", "PNG")
    img.save(img_dir / "duplicate_2.png", "PNG")

    return img_dir


class TestScanManager:
    """扫描管理器测试"""

    def test_create_scan_run(self, scan_manager, sample_directory):
        """测试创建扫描任务"""
        scan_run = scan_manager.create_scan_run(str(sample_directory))

        assert scan_run.id is not None
        assert scan_run.root_path == str(sample_directory)
        assert scan_run.status == ScanStatus.PENDING

    def test_get_scan_run(self, scan_manager, sample_directory):
        """测试获取扫描任务"""
        scan_run = scan_manager.create_scan_run(str(sample_directory))
        retrieved = scan_manager.get_scan_run(scan_run.id)

        assert retrieved is not None
        assert retrieved.id == scan_run.id
        assert retrieved.root_path == scan_run.root_path

    def test_get_scan_run_not_found(self, scan_manager):
        """测试获取不存在的扫描任务"""
        retrieved = scan_manager.get_scan_run("nonexistent-id")
        assert retrieved is None

    def test_list_scan_runs(self, scan_manager, sample_directory):
        """测试列出扫描任务"""
        # 创建多个扫描任务
        scan_manager.create_scan_run(str(sample_directory))
        scan_manager.create_scan_run(str(sample_directory))

        runs = scan_manager.list_scan_runs()
        assert len(runs) == 2

    def test_start_scan(self, scan_manager, sample_directory):
        """测试执行扫描"""
        scan_run = scan_manager.create_scan_run(str(sample_directory))
        result = scan_manager.start_scan(scan_run.id)

        assert result.status == ScanStatus.COMPLETED
        assert result.total_files == 7  # 5 unique + 2 duplicates
        assert result.scanned_files == 7

    def test_start_scan_with_duplicates(self, scan_manager, sample_directory):
        """测试执行扫描并检测重复"""
        scan_run = scan_manager.create_scan_run(str(sample_directory))
        result = scan_manager.start_scan(scan_run.id)

        # 获取重复组
        groups = scan_manager.get_duplicate_groups(scan_run.id)

        # 应该有完全重复组（3 个红色图片：test_0.png, duplicate_1.png, duplicate_2.png）
        exact_groups = [g for g in groups if g.kind.value == "exact"]
        assert len(exact_groups) == 1
        assert len(exact_groups[0].asset_ids) == 3

    def test_start_scan_nonexistent(self, scan_manager):
        """测试执行不存在的扫描任务"""
        with pytest.raises(ValueError, match="扫描任务不存在"):
            scan_manager.start_scan("nonexistent-id")

    def test_start_scan_wrong_status(self, scan_manager, sample_directory):
        """测试执行状态错误的扫描任务"""
        scan_run = scan_manager.create_scan_run(str(sample_directory))
        # 先执行一次
        scan_manager.start_scan(scan_run.id)

        # 再次执行应该失败
        with pytest.raises(ValueError, match="扫描任务状态不允许执行"):
            scan_manager.start_scan(scan_run.id)

    def test_get_assets_by_scan(self, scan_manager, sample_directory):
        """测试获取扫描任务的资产"""
        scan_run = scan_manager.create_scan_run(str(sample_directory))
        scan_manager.start_scan(scan_run.id)

        assets = scan_manager.get_assets_by_scan(scan_run.id)
        assert len(assets) == 7

        for asset in assets:
            assert asset.scan_run_id == scan_run.id
            assert asset.sha256 is not None
            assert asset.phash is not None

    def test_get_duplicate_groups(self, scan_manager, sample_directory):
        """测试获取重复组"""
        scan_run = scan_manager.create_scan_run(str(sample_directory))
        scan_manager.start_scan(scan_run.id)

        groups = scan_manager.get_duplicate_groups(scan_run.id)
        assert len(groups) >= 1

        for group in groups:
            assert group.scan_run_id == scan_run.id
            assert len(group.asset_ids) >= 2
