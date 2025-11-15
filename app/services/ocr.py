"""OCR 识别服务"""

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from PIL import Image

from app.storage.models import OcrResult

logger = logging.getLogger(__name__)


class OcrEngine(ABC):
    """OCR 引擎基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎名称"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """引擎版本"""
        pass

    @abstractmethod
    def recognize(self, image_path: str, language: str = "ch") -> tuple[str, float]:
        """识别图片中的文字

        Args:
            image_path: 图片路径
            language: 识别语言

        Returns:
            (识别文本, 置信度) 元组
        """
        pass


class PillowOcrEngine(OcrEngine):
    """基于 Pillow 的简单 OCR 引擎（占位实现）

    这是一个简化的占位实现，用于测试和开发。
    生产环境应使用 PaddleOCR 或 Tesseract。
    """

    @property
    def name(self) -> str:
        return "pillow_placeholder"

    @property
    def version(self) -> str:
        return "0.1.0"

    def recognize(self, image_path: str, language: str = "ch") -> tuple[str, float]:
        """简单 OCR 实现（占位）"""
        try:
            with Image.open(image_path) as img:
                # 占位实现：返回图片基本信息
                width, height = img.size
                mode = img.mode
                text = f"[图片信息] 尺寸: {width}x{height}, 模式: {mode}"
                return text, 0.5
        except Exception as e:
            logger.error(f"OCR 识别失败 {image_path}: {e}")
            return "", 0.0


class OcrService:
    """OCR 识别服务"""

    def __init__(self, engine: Optional[OcrEngine] = None):
        self.engine = engine or PillowOcrEngine()

    def run_ocr(
        self,
        image_path: str,
        asset_id: str,
        language: str = "ch",
    ) -> OcrResult:
        """执行 OCR 识别

        Args:
            image_path: 图片路径
            asset_id: 关联的资产 ID
            language: 识别语言

        Returns:
            OcrResult 模型
        """
        if not Path(image_path).exists():
            raise ValueError(f"图片文件不存在: {image_path}")

        text, confidence = self.engine.recognize(image_path, language)

        result = OcrResult(
            asset_id=asset_id,
            engine=self.engine.name,
            engine_version=self.engine.version,
            language=language,
            text=text,
            confidence=confidence,
            is_sensitive=False,
        )

        logger.debug(f"OCR 完成: {image_path}, 置信度: {confidence:.2f}")
        return result

    def batch_ocr(
        self,
        image_paths: list[str],
        asset_ids: list[str],
        language: str = "ch",
    ) -> list[OcrResult]:
        """批量 OCR 识别

        Args:
            image_paths: 图片路径列表
            asset_ids: 资产 ID 列表
            language: 识别语言

        Returns:
            OcrResult 模型列表
        """
        if len(image_paths) != len(asset_ids):
            raise ValueError("图片路径和资产 ID 数量不匹配")

        results = []
        for image_path, asset_id in zip(image_paths, asset_ids):
            try:
                result = self.run_ocr(image_path, asset_id, language)
                results.append(result)
            except Exception as e:
                logger.error(f"批量 OCR 失败 {image_path}: {e}")
                # 添加空结果
                results.append(
                    OcrResult(
                        asset_id=asset_id,
                        engine=self.engine.name,
                        engine_version=self.engine.version,
                        language=language,
                        text="",
                        confidence=0.0,
                    )
                )

        return results


def get_available_engines() -> list[str]:
    """获取可用的 OCR 引擎列表"""
    engines = ["pillow_placeholder"]

    # 检查 PaddleOCR
    try:
        import paddleocr
        engines.append("paddleocr")
    except ImportError:
        pass

    # 检查 Tesseract
    try:
        import pytesseract
        engines.append("tesseract")
    except ImportError:
        pass

    return engines
