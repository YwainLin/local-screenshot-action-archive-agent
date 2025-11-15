"""图像指纹服务"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


class FingerprintService:
    """图像指纹计算服务"""

    def __init__(self, thumbnail_max_size: int = 256):
        self.thumbnail_max_size = thumbnail_max_size

    def compute_sha256(self, file_path: str) -> str:
        """计算文件 SHA-256 哈希

        Args:
            file_path: 文件路径

        Returns:
            十六进制哈希字符串
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def compute_phash(self, file_path: str, hash_size: int = 16) -> str:
        """计算感知哈希 (pHash)

        基于 DCT 变换的感知哈希，对图像缩放、压缩等变换具有鲁棒性。

        Args:
            file_path: 图像文件路径
            hash_size: 哈希大小（位数）

        Returns:
            十六进制哈希字符串
        """
        try:
            img = Image.open(file_path)

            # 转换为灰度图
            if img.mode != "L":
                img = img.convert("L")

            # 缩放到 hash_size+1 x hash_size+1
            resize_size = hash_size + 1
            img = img.resize((resize_size, resize_size), Image.Resampling.LANCZOS)

            # 转换为像素列表
            pixels = list(img.getdata())

            # 简化的 pHash：计算相邻像素差异
            # 这是一个简化版本，实际 pHash 使用 DCT 变换
            hash_bits = []
            for y in range(hash_size):
                for x in range(hash_size):
                    idx = y * resize_size + x
                    # 比较当前像素与右侧和下方像素
                    if pixels[idx] > pixels[idx + 1]:  # 水平差异
                        hash_bits.append(1)
                    else:
                        hash_bits.append(0)
                    if pixels[idx] > pixels[idx + resize_size]:  # 垂直差异
                        hash_bits.append(1)
                    else:
                        hash_bits.append(0)

            # 转换为十六进制
            hex_str = ""
            for i in range(0, len(hash_bits), 4):
                nibble = 0
                for j in range(4):
                    if i + j < len(hash_bits):
                        nibble = (nibble << 1) | hash_bits[i + j]
                    else:
                        nibble <<= 1
                hex_str += format(nibble, "x")

            return hex_str

        except Exception as e:
            logger.error(f"计算 pHash 失败 {file_path}: {e}")
            raise

    def compute_dhash(self, file_path: str, hash_size: int = 16) -> str:
        """计算差异哈希 (dHash)

        基于相邻像素差异的哈希，计算速度比 pHash 快。

        Args:
            file_path: 图像文件路径
            hash_size: 哈希大小（位数）

        Returns:
            十六进制哈希字符串
        """
        try:
            img = Image.open(file_path)

            # 转换为灰度图
            if img.mode != "L":
                img = img.convert("L")

            # 缩放到 hash_size+1 x hash_size
            img = img.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)

            # 获取像素数据
            pixels = list(img.getdata())

            # 计算相邻像素差异
            hash_bits = []
            for y in range(hash_size):
                for x in range(hash_size):
                    idx = y * (hash_size + 1) + x
                    if pixels[idx] < pixels[idx + 1]:
                        hash_bits.append(1)
                    else:
                        hash_bits.append(0)

            # 转换为十六进制
            hex_str = ""
            for i in range(0, len(hash_bits), 4):
                nibble = 0
                for j in range(4):
                    if i + j < len(hash_bits):
                        nibble = (nibble << 1) | hash_bits[i + j]
                    else:
                        nibble <<= 1
                hex_str += format(nibble, "x")

            return hex_str

        except Exception as e:
            logger.error(f"计算 dHash 失败 {file_path}: {e}")
            raise

    def compute_image_size(self, file_path: str) -> tuple[int, int]:
        """获取图像尺寸

        Args:
            file_path: 图像文件路径

        Returns:
            (宽度, 高度) 元组
        """
        try:
            with Image.open(file_path) as img:
                return img.size
        except Exception as e:
            logger.error(f"获取图像尺寸失败 {file_path}: {e}")
            raise

    def generate_thumbnail(
        self, file_path: str, output_path: str, max_size: Optional[int] = None
    ) -> str:
        """生成缩略图

        Args:
            file_path: 源图像路径
            output_path: 缩略图输出路径
            max_size: 最大尺寸（像素），默认使用实例配置

        Returns:
            缩略图路径
        """
        if max_size is None:
            max_size = self.thumbnail_max_size

        try:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)

            with Image.open(file_path) as img:
                # 保持宽高比缩放
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                img.save(output_path)
                logger.debug(f"生成缩略图: {output_path}")
                return output_path

        except Exception as e:
            logger.error(f"生成缩略图失败 {file_path}: {e}")
            raise

    def hash_distance(self, hash1: str, hash2: str) -> int:
        """计算两个哈希之间的汉明距离

        Args:
            hash1: 第一个哈希字符串
            hash2: 第二个哈希字符串

        Returns:
            汉明距离（不同位的数量）
        """
        if len(hash1) != len(hash2):
            raise ValueError("哈希长度不一致")

        # 转换为整数进行比较
        try:
            val1 = int(hash1, 16)
            val2 = int(hash2, 16)
        except ValueError:
            raise ValueError("无效的十六进制哈希")

        # 计算异或后 1 的数量
        xor = val1 ^ val2
        distance = bin(xor).count("1")
        return distance
