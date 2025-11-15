"""图像指纹单元测试"""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from app.services.fingerprint import FingerprintService


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def fingerprint():
    """创建指纹服务实例"""
    return FingerprintService()


@pytest.fixture
def sample_image(temp_dir):
    """创建示例图片"""
    img = Image.new("RGB", (200, 200), color="red")
    img_path = temp_dir / "test.png"
    img.save(img_path, "PNG")
    return img_path


@pytest.fixture
def sample_image_copy(temp_dir):
    """创建示例图片副本"""
    img = Image.new("RGB", (200, 200), color="red")
    img_path = temp_dir / "test_copy.png"
    img.save(img_path, "PNG")
    return img_path


@pytest.fixture
def different_image(temp_dir):
    """创建不同的图片"""
    img = Image.new("RGB", (200, 200), color="blue")
    img_path = temp_dir / "different.png"
    img.save(img_path, "PNG")
    return img_path


class TestFingerprintService:
    """指纹服务测试"""

    def test_compute_sha256(self, fingerprint, sample_image):
        """测试 SHA-256 计算"""
        sha256 = fingerprint.compute_sha256(str(sample_image))
        assert len(sha256) == 64  # SHA-256 是 64 位十六进制
        assert all(c in "0123456789abcdef" for c in sha256)

    def test_compute_sha256_same_file(self, fingerprint, sample_image, sample_image_copy):
        """测试相同文件的 SHA-256"""
        sha256_1 = fingerprint.compute_sha256(str(sample_image))
        sha256_2 = fingerprint.compute_sha256(str(sample_image_copy))
        assert sha256_1 == sha256_2

    def test_compute_sha256_different_file(self, fingerprint, sample_image, different_image):
        """测试不同文件的 SHA-256"""
        sha256_1 = fingerprint.compute_sha256(str(sample_image))
        sha256_2 = fingerprint.compute_sha256(str(different_image))
        assert sha256_1 != sha256_2

    def test_compute_phash(self, fingerprint, sample_image):
        """测试 pHash 计算"""
        phash = fingerprint.compute_phash(str(sample_image))
        assert len(phash) > 0
        assert all(c in "0123456789abcdef" for c in phash)

    def test_compute_dhash(self, fingerprint, sample_image):
        """测试 dHash 计算"""
        dhash = fingerprint.compute_dhash(str(sample_image))
        assert len(dhash) > 0
        assert all(c in "0123456789abcdef" for c in dhash)

    def test_compute_image_size(self, fingerprint, sample_image):
        """测试获取图像尺寸"""
        width, height = fingerprint.compute_image_size(str(sample_image))
        assert width == 200
        assert height == 200

    def test_generate_thumbnail(self, fingerprint, temp_dir, sample_image):
        """测试生成缩略图"""
        thumbnail_path = str(temp_dir / "thumbnail.png")
        result = fingerprint.generate_thumbnail(str(sample_image), thumbnail_path)

        assert result == thumbnail_path
        assert Path(thumbnail_path).exists()

        # 验证缩略图尺寸
        with Image.open(thumbnail_path) as img:
            assert img.width <= 256
            assert img.height <= 256

    def test_generate_thumbnail_custom_size(self, fingerprint, temp_dir, sample_image):
        """测试自定义尺寸缩略图"""
        thumbnail_path = str(temp_dir / "thumbnail_small.png")
        result = fingerprint.generate_thumbnail(str(sample_image), thumbnail_path, max_size=100)

        assert result == thumbnail_path
        assert Path(thumbnail_path).exists()

        with Image.open(thumbnail_path) as img:
            assert img.width <= 100
            assert img.height <= 100

    def test_hash_distance_same(self, fingerprint):
        """测试相同哈希的距离"""
        distance = fingerprint.hash_distance("abc123", "abc123")
        assert distance == 0

    def test_hash_distance_different(self, fingerprint):
        """测试不同哈希的距离"""
        distance = fingerprint.hash_distance("000000", "fffff0")
        assert distance > 0

    def test_hash_distance_different_length(self, fingerprint):
        """测试不同长度哈希的距离"""
        with pytest.raises(ValueError, match="哈希长度不一致"):
            fingerprint.hash_distance("abc", "abcd")

    def test_hash_distance_invalid_hex(self, fingerprint):
        """测试无效十六进制哈希"""
        with pytest.raises(ValueError, match="无效的十六进制哈希"):
            fingerprint.hash_distance("xyz", "xyz")
