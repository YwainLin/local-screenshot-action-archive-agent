"""工作区配置服务单元测试"""

import json
import tempfile
from pathlib import Path

import pytest

from app.services.workspace import WorkspaceService
from app.storage.models import WorkspaceConfig


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def workspace_service(temp_dir):
    """创建工作区服务实例"""
    return WorkspaceService(config_dir=str(temp_dir))


@pytest.fixture
def sample_config():
    """示例工作区配置"""
    return WorkspaceConfig(
        workspace_id="test-workspace",
        root_path="/tmp/screenshots",
        allowed_export_paths=["/tmp/exports"],
    )


class TestWorkspaceService:
    """工作区配置服务测试"""

    def test_create_workspace(self, workspace_service, temp_dir):
        """测试创建工作区"""
        screenshots_dir = temp_dir / "screenshots"
        screenshots_dir.mkdir()

        config = workspace_service.create_workspace(
            workspace_id="test",
            root_path=str(screenshots_dir),
        )

        assert config.workspace_id == "test"
        assert config.root_path == str(screenshots_dir.resolve())
        assert workspace_service.config_file.exists()

    def test_create_workspace_nonexistent_dir(self, workspace_service):
        """测试创建不存在目录的工作区"""
        with pytest.raises(ValueError, match="目录不存在"):
            workspace_service.create_workspace(
                workspace_id="test",
                root_path="/nonexistent/path",
            )

    def test_save_and_load_config(self, workspace_service, sample_config):
        """测试保存和加载配置"""
        workspace_service.save_config(sample_config)
        loaded = workspace_service.load_config()

        assert loaded is not None
        assert loaded.workspace_id == sample_config.workspace_id
        assert loaded.root_path == sample_config.root_path

    def test_load_config_not_exists(self, workspace_service):
        """测试加载不存在的配置"""
        config = workspace_service.load_config()
        assert config is None

    def test_load_config_invalid_json(self, workspace_service, temp_dir):
        """测试加载无效 JSON 配置"""
        invalid_file = temp_dir / "config.json"
        invalid_file.write_text("invalid json", encoding="utf-8")

        with pytest.raises(ValueError, match="配置文件格式错误"):
            workspace_service.load_config()

    def test_validate_path_access_within_root(self, workspace_service, temp_dir):
        """测试路径访问验证 - 根目录内"""
        screenshots_dir = temp_dir / "screenshots"
        screenshots_dir.mkdir()
        sub_dir = screenshots_dir / "sub"
        sub_dir.mkdir()

        config = WorkspaceConfig(
            workspace_id="test",
            root_path=str(screenshots_dir),
        )

        assert workspace_service.validate_path_access(config, str(sub_dir)) is True
        assert workspace_service.validate_path_access(config, str(screenshots_dir)) is True

    def test_validate_path_access_outside_root(self, workspace_service, temp_dir):
        """测试路径访问验证 - 根目录外"""
        screenshots_dir = temp_dir / "screenshots"
        screenshots_dir.mkdir()
        other_dir = temp_dir / "other"
        other_dir.mkdir()

        config = WorkspaceConfig(
            workspace_id="test",
            root_path=str(screenshots_dir),
        )

        assert workspace_service.validate_path_access(config, str(other_dir)) is False

    def test_validate_path_access_export_path(self, workspace_service, temp_dir):
        """测试路径访问验证 - 导出路径"""
        screenshots_dir = temp_dir / "screenshots"
        screenshots_dir.mkdir()
        exports_dir = temp_dir / "exports"
        exports_dir.mkdir()

        config = WorkspaceConfig(
            workspace_id="test",
            root_path=str(screenshots_dir),
            allowed_export_paths=[str(exports_dir)],
        )

        assert workspace_service.validate_path_access(config, str(exports_dir)) is True

    def test_validate_path_access_path_traversal(self, workspace_service, temp_dir):
        """测试路径访问验证 - 路径遍历攻击"""
        screenshots_dir = temp_dir / "screenshots"
        screenshots_dir.mkdir()

        config = WorkspaceConfig(
            workspace_id="test",
            root_path=str(screenshots_dir),
        )

        # 尝试通过 .. 访问上级目录
        traversal_path = screenshots_dir / ".." / "other"
        assert workspace_service.validate_path_access(config, str(traversal_path)) is False

    def test_get_workspace_root(self, workspace_service, temp_dir):
        """测试获取工作区根目录"""
        screenshots_dir = temp_dir / "screenshots"
        screenshots_dir.mkdir()

        config = WorkspaceConfig(
            workspace_id="test",
            root_path=str(screenshots_dir),
        )

        root = workspace_service.get_workspace_root(config)
        assert root == screenshots_dir.resolve()

    def test_get_thumbnails_dir(self, workspace_service, temp_dir):
        """测试获取缩略图目录"""
        screenshots_dir = temp_dir / "screenshots"
        screenshots_dir.mkdir()

        config = WorkspaceConfig(
            workspace_id="test",
            root_path=str(screenshots_dir),
        )

        thumbnails_dir = workspace_service.get_thumbnails_dir(config)
        assert thumbnails_dir == screenshots_dir.resolve() / "thumbnails"

    def test_get_exports_dir(self, workspace_service, temp_dir):
        """测试获取导出目录"""
        screenshots_dir = temp_dir / "screenshots"
        screenshots_dir.mkdir()

        config = WorkspaceConfig(
            workspace_id="test",
            root_path=str(screenshots_dir),
        )

        exports_dir = workspace_service.get_exports_dir(config)
        assert exports_dir == screenshots_dir.resolve() / "exports"

    def test_get_audit_dir(self, workspace_service, temp_dir):
        """测试获取审计日志目录"""
        screenshots_dir = temp_dir / "screenshots"
        screenshots_dir.mkdir()

        config = WorkspaceConfig(
            workspace_id="test",
            root_path=str(screenshots_dir),
        )

        audit_dir = workspace_service.get_audit_dir(config)
        assert audit_dir == screenshots_dir.resolve() / "audit"
