from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image

try:
    from paddleocr import PaddleOCR

    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False


class OcrService:
    """OCR 文字识别服务"""

    def __init__(self, language: str = "ch", use_gpu: bool = False) -> None:
        self.language = language
        self.ocr_engine = None
        if PADDLEOCR_AVAILABLE:
            try:
                self.ocr_engine = PaddleOCR(
                    use_angle_cls=True,
                    lang=language,
                    use_gpu=use_gpu,
                    show_log=False,
                )
            except Exception:
                self.ocr_engine = None

    @property
    def is_available(self) -> bool:
        return self.ocr_engine is not None

    def recognize(
        self,
        image_path: Path,
        confidence_threshold: float = 0.5,
    ) -> dict:
        """识别图片中的文字"""
        if not self.is_available:
            return {
                "text": "",
                "confidence": 0.0,
                "language": self.language,
                "engine": "paddleocr",
                "engine_version": "unavailable",
                "error": "PaddleOCR not available",
            }

        try:
            image_path = Path(image_path)
            if not image_path.exists():
                return {
                    "text": "",
                    "confidence": 0.0,
                    "language": self.language,
                    "engine": "paddleocr",
                    "engine_version": "unknown",
                    "error": f"File not found: {image_path}",
                }

            result = self.ocr_engine.ocr(str(image_path), cls=True)

            if result is None or len(result) == 0:
                return {
                    "text": "",
                    "confidence": 0.0,
                    "language": self.language,
                    "engine": "paddleocr",
                    "engine_version": "unknown",
                    "error": "No text detected",
                }

            texts = []
            confidences = []

            for line in result:
                if line is None:
                    continue
                for item in line:
                    if item is None or len(item) < 2:
                        continue
                    text = item[1][0]
                    conf = item[1][1]
                    if conf >= confidence_threshold:
                        texts.append(text)
                        confidences.append(conf)

            full_text = "\n".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            return {
                "text": full_text,
                "confidence": avg_confidence,
                "language": self.language,
                "engine": "paddleocr",
                "engine_version": "latest",
                "error": None,
            }

        except Exception as e:
            return {
                "text": "",
                "confidence": 0.0,
                "language": self.language,
                "engine": "paddleocr",
                "engine_version": "unknown",
                "error": str(e),
            }

    def batch_recognize(
        self,
        image_paths: list[Path],
        confidence_threshold: float = 0.5,
    ) -> list[dict]:
        """批量识别图片文字"""
        results = []
        for path in image_paths:
            result = self.recognize(path, confidence_threshold)
            results.append(result)
        return results


def get_ocr_service(language: str = "ch", use_gpu: bool = False) -> OcrService:
    """获取 OCR 服务实例"""
    return OcrService(language=language, use_gpu=use_gpu)
