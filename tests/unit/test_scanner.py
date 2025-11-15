"""文件扫描器单元测试"""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from app.services.scanner import ScannerService


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def scanner():
    """创建扫描器实例"""
    return ScannerService()


@pytest.fixture
def sample_images(temp_dir):
    """创建示例图片"""
    images = []

    # 创建 PNG 图片
    png_path = temp_dir / "test1.png"
    img = Image.new("RGB", (100, 100), color="red")
    img.save(png_path, "PNG")
    images.append(png_path)

    # 创建 JPG 图片
    jpg_path = temp_dir / "test2.jpg"
    img = Image.new("RGB", (100, 100), color="green")
    img.save(jpg_path, "JPEG")
    images.append(jpg_path)

    # 创建 WebP 图片
    webp_path = temp_dir / "test3.webp"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(webp_path, "WEBP")
    images.append(webp_path)

    # 创建不支持的文件
    txt_path = temp_dir / "test.txt"
    txt_path.write_text("not an image")
    images.append(txt_path)

    return images


class TestScannerService:
    """扫描器测试"""

    def test_list_assets(self, scanner, temp_dir, sample_images):
        """测试列出资产"""
        assets = scanner.list_assets(str(temp_dir), "scan-1")

        # 应该只返回支持的图片格式
        assert len(assets) == 3
        filenames = {a.filename for a in assets}
        assert "test1.png" in filenames
        assert "test2.jpg" in filenames
        assert "test3.webp" in filenames
        assert "test.txt" not in filenames

    def test_list_assets_with_subdirectories(self, scanner, temp_dir):
        """测试扫描子目录"""
        # 创建子目录和图片
        sub_dir = temp_dir / "subdir"
        sub_dir.mkdir()

        img = Image.new("RGB", (100, 100), color="red")
        img.save(temp_dir / "test1.png", "PNG")
        img.save(sub_dir / "test2.png", "PNG")

        assets = scanner.list_assets(str(temp_dir), "scan-1")
        assert len(assets) == 2

    def test_list_assets_empty_directory(self, scanner, temp_dir):
        """测试扫描空目录"""
        assets = scanner.list_assets(str(temp_dir), "scan-1")
        assert len(assets) == 0

    def test_list_assets_nonexistent_directory(self, scanner):
        """测试扫描不存在的目录"""
        with pytest.raises(ValueError, match="目录不存在"):
            scanner.list_assets("/nonexistent/path", "scan-1")

    def test_list_assets_not_directory(self, scanner, temp_dir):
        """测试扫描文件而非目录"""
        file_path = temp_dir / "test.txt"
        file_path.write_text("test")

        with pytest.raises(ValueError, match="路径不是目录"):
            scanner.list_assets(str(file_path), "scan-1")

    def test_list_assets_metadata(self, scanner, temp_dir, sample_images):
        """测试资产元数据"""
        assets = scanner.list_assets(str(temp_dir), "scan-1")

        for asset in assets:
            assert asset.scan_run_id == "scan-1"
            assert asset.path
            assert asset.filename
            assert asset.size > 0
            assert asset.mtime is not None

    def test_get_file_stats(self, scanner, temp_dir, sample_images):
        """测试获取文件统计"""
        stats = scanner.get_file_stats(str(temp_dir))

        assert stats["total_files"] == 4  # 3 images + 1 txt
        assert stats["supported_files"] == 3
        assert stats["unsupported_files"] == 1
        assert stats["total_size"] > 0
        assert stats["supported_size"] > 0
        assert ".png" in stats["extension_counts"]
        assert ".jpg" in stats["extension_counts"]
        assert ".webp" in stats["extension_counts"]
        assert ".txt" in stats["extension_counts"]

    def test_get_file_stats_nonexistent_directory(self, scanner):
        """测试获取不存在目录的统计"""
        with pytest.raises(ValueError, match="目录不存在"):
            scanner.get_file_stats("/nonexistent/path")
