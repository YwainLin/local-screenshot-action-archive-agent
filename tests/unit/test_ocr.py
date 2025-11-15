"""OCR 服务单元测试"""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from app.services.ocr import OcrService, PillowOcrEngine, get_available_engines
from app.storage.models import OcrResult


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def ocr_service():
    """创建 OCR 服务实例"""
    return OcrService()


@pytest.fixture
def sample_image(temp_dir):
    """创建示例图片"""
    img = Image.new("RGB", (200, 200), color="white")
    img_path = temp_dir / "test.png"
    img.save(img_path, "PNG")
    return img_path


class TestOcrService:
    """OCR 服务测试"""

    def test_run_ocr(self, ocr_service, sample_image):
        """测试 OCR 识别"""
        result = ocr_service.run_ocr(str(sample_image), "asset-1")

        assert isinstance(result, OcrResult)
        assert result.asset_id == "asset-1"
        assert result.engine == "pillow_placeholder"
        assert result.text
        assert result.confidence > 0

    def test_run_ocr_with_language(self, ocr_service, sample_image):
        """测试指定语言 OCR"""
        result = ocr_service.run_ocr(str(sample_image), "asset-1", language="en")

        assert result.language == "en"

    def test_run_ocr_nonexistent_file(self, ocr_service):
        """测试识别不存在的文件"""
        with pytest.raises(ValueError, match="图片文件不存在"):
            ocr_service.run_ocr("/nonexistent/image.png", "asset-1")

    def test_batch_ocr(self, ocr_service, temp_dir):
        """测试批量 OCR"""
        images = []
        for i in range(3):
            img = Image.new("RGB", (100, 100), color="white")
            img_path = temp_dir / f"test_{i}.png"
            img.save(img_path, "PNG")
            images.append(str(img_path))

        asset_ids = [f"asset-{i}" for i in range(3)]

        results = ocr_service.batch_ocr(images, asset_ids)

        assert len(results) == 3
        for result, asset_id in zip(results, asset_ids):
            assert result.asset_id == asset_id

    def test_batch_ocr_mismatched_lengths(self, ocr_service):
        """测试批量 OCR 数量不匹配"""
        with pytest.raises(ValueError, match="数量不匹配"):
            ocr_service.batch_ocr(["a.png", "b.png"], ["asset-1"])


class TestPillowOcrEngine:
    """Pillow OCR 引擎测试"""

    def test_engine_properties(self):
        """测试引擎属性"""
        engine = PillowOcrEngine()
        assert engine.name == "pillow_placeholder"
        assert engine.version == "0.1.0"

    def test_recognize(self, temp_dir):
        """测试识别功能"""
        engine = PillowOcrEngine()

        img = Image.new("RGB", (100, 100), color="white")
        img_path = temp_dir / "test.png"
        img.save(img_path, "PNG")

        text, confidence = engine.recognize(str(img_path))

        assert text
        assert confidence > 0


class TestGetAvailableEngines:
    """获取可用引擎测试"""

    def test_get_engines(self):
        """测试获取引擎列表"""
        engines = get_available_engines()
        assert "pillow_placeholder" in engines
        assert isinstance(engines, list)
