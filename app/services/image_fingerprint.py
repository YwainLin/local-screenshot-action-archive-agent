from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from PIL import Image

try:
    import imagehash

    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False


class ImageFingerprintService:
    """图像指纹计算服务"""

    def __init__(self, thumbnail_dir: Optional[Path] = None) -> None:
        self.thumbnail_dir = thumbnail_dir
        if self.thumbnail_dir:
            self.thumbnail_dir.mkdir(parents=True, exist_ok=True)

    def compute_sha256(self, file_path: Path) -> str:
        """计算文件 SHA-256 哈希"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def compute_phash(self, file_path: Path) -> Optional[str]:
        """计算感知哈希（pHash）"""
        if not IMAGEHASH_AVAILABLE:
            return None

        try:
            with Image.open(file_path) as img:
                phash = imagehash.phash(img)
                return str(phash)
        except Exception:
            return None

    def generate_thumbnail(
        self,
        file_path: Path,
        size: tuple[int, int] = (256, 256),
    ) -> Optional[Path]:
        """生成缩略图"""
        if not self.thumbnail_dir:
            return None

        try:
            with Image.open(file_path) as img:
                img.thumbnail(size, Image.Resampling.LANCZOS)

                thumb_name = f"{file_path.stem}_thumb{file_path.suffix}"
                thumb_path = self.thumbnail_dir / thumb_name

                if file_path.suffix.lower() == ".png":
                    img.save(thumb_path, "PNG", optimize=True)
                else:
                    img.save(thumb_path, "JPEG", quality=85, optimize=True)

                return thumb_path
        except Exception:
            return None

    def get_image_dimensions(self, file_path: Path) -> Optional[tuple[int, int]]:
        """获取图片尺寸"""
        try:
            with Image.open(file_path) as img:
                return img.size
        except Exception:
            return None

    def compute_fingerprint(
        self,
        file_path: Path,
        generate_thumb: bool = True,
        thumbnail_size: tuple[int, int] = (256, 256),
    ) -> dict:
        """计算完整的图像指纹"""
        sha256 = self.compute_sha256(file_path)
        phash = self.compute_phash(file_path)
        dimensions = self.get_image_dimensions(file_path)

        thumb_path = None
        if generate_thumb:
            thumb_path = self.generate_thumbnail(file_path, thumbnail_size)

        return {
            "sha256": sha256,
            "phash": phash,
            "width": dimensions[0] if dimensions else None,
            "height": dimensions[1] if dimensions else None,
            "thumbnail_path": str(thumb_path) if thumb_path else None,
        }


def hash_distance(hash1: str, hash2: str) -> int:
    """计算两个哈希之间的汉明距离"""
    if not IMAGEHASH_AVAILABLE:
        return -1

    try:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        return h1 - h2
    except Exception:
        return -1
