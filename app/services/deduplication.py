"""重复检测服务"""

import logging
from collections import defaultdict
from typing import Optional

from app.services.fingerprint import FingerprintService
from app.storage.models import Asset, DuplicateGroup, DuplicateKind

logger = logging.getLogger(__name__)


class DeduplicationService:
    """重复检测服务"""

    def __init__(self, fingerprint_service: Optional[FingerprintService] = None):
        self.fingerprint_service = fingerprint_service or FingerprintService()

    def find_exact_duplicates(self, assets: list[Asset]) -> list[DuplicateGroup]:
        """查找完全重复的图片（SHA-256 相同）

        Args:
            assets: 资产列表（需要已计算 sha256）

        Returns:
            完全重复组列表
        """
        # 按 SHA-256 分组
        hash_groups: dict[str, list[Asset]] = defaultdict(list)
        for asset in assets:
            if asset.sha256:
                hash_groups[asset.sha256].append(asset)

        # 找出重复组
        groups = []
        for sha256, group_assets in hash_groups.items():
            if len(group_assets) < 2:
                continue

            # 选择第一个作为代表
            representative = group_assets[0]
            group = DuplicateGroup(
                scan_run_id=representative.scan_run_id,
                kind=DuplicateKind.EXACT,
                representative_asset_id=representative.id or "",
                asset_ids=[a.id for a in group_assets if a.id],
            )
            groups.append(group)

        logger.info(f"发现 {len(groups)} 组完全重复")
        return groups

    def find_near_duplicates(
        self, assets: list[Asset], threshold: int = 10
    ) -> list[DuplicateGroup]:
        """查找近似重复的图片（pHash 距离 ≤ 阈值）

        使用 Union-Find 算法将相似图片分组。

        Args:
            assets: 资产列表（需要已计算 phash）
            threshold: pHash 距离阈值

        Returns:
            近似重复组列表
        """
        # 过滤出有 phash 的资产
        assets_with_phash = [a for a in assets if a.phash]
        if len(assets_with_phash) < 2:
            return []

        # Union-Find 数据结构
        parent = {a.id: a.id for a in assets_with_phash if a.id}
        rank = {a.id: 0 for a in assets_with_phash if a.id}

        def find(x: str) -> str:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: str, y: str) -> None:
            px, py = find(x), find(y)
            if px == py:
                return
            if rank[px] < rank[py]:
                px, py = py, px
            parent[py] = px
            if rank[px] == rank[py]:
                rank[px] += 1

        # 比较所有资产对
        for i in range(len(assets_with_phash)):
            for j in range(i + 1, len(assets_with_phash)):
                a1, a2 = assets_with_phash[i], assets_with_phash[j]
                if not a1.id or not a2.id:
                    continue
                if not a1.phash or not a2.phash:
                    continue

                distance = self.fingerprint_service.hash_distance(a1.phash, a2.phash)
                if distance <= threshold:
                    union(a1.id, a2.id)

        # 收集分组
        groups_map: dict[str, list[Asset]] = defaultdict(list)
        asset_map = {a.id: a for a in assets_with_phash if a.id}

        for asset_id in parent:
            root = find(asset_id)
            if asset_id in asset_map:
                groups_map[root].append(asset_map[asset_id])

        # 创建重复组
        groups = []
        for representative_id, group_assets in groups_map.items():
            if len(group_assets) < 2:
                continue

            # 计算代表与组内其他图片的平均距离
            rep_asset = asset_map[representative_id]
            distances = []
            for a in group_assets:
                if a.id != representative_id and a.phash and rep_asset.phash:
                    dist = self.fingerprint_service.hash_distance(rep_asset.phash, a.phash)
                    distances.append(dist)

            avg_distance = sum(distances) // len(distances) if distances else 0

            group = DuplicateGroup(
                scan_run_id=rep_asset.scan_run_id,
                kind=DuplicateKind.NEAR,
                representative_asset_id=representative_id,
                distance=avg_distance,
                asset_ids=[a.id for a in group_assets if a.id],
            )
            groups.append(group)

        logger.info(f"发现 {len(groups)} 组近似重复")
        return groups

    def process_assets(self, assets: list[Asset], threshold: int = 10) -> list[DuplicateGroup]:
        """处理资产列表，计算指纹并检测重复

        Args:
            assets: 原始资产列表
            threshold: 近似重复阈值

        Returns:
            所有重复组列表（完全重复 + 近似重复）
        """
        # 计算 SHA-256
        for asset in assets:
            if not asset.sha256 and asset.path:
                try:
                    asset.sha256 = self.fingerprint_service.compute_sha256(asset.path)
                except Exception as e:
                    logger.error(f"计算 SHA-256 失败 {asset.path}: {e}")

        # 计算 pHash
        for asset in assets:
            if not asset.phash and asset.path:
                try:
                    asset.phash = self.fingerprint_service.compute_phash(asset.path)
                except Exception as e:
                    logger.error(f"计算 pHash 失败 {asset.path}: {e}")

        # 获取图像尺寸
        for asset in assets:
            if not asset.width and asset.path:
                try:
                    width, height = self.fingerprint_service.compute_image_size(asset.path)
                    asset.width = width
                    asset.height = height
                except Exception as e:
                    logger.error(f"获取图像尺寸失败 {asset.path}: {e}")

        # 检测重复
        exact_groups = self.find_exact_duplicates(assets)
        near_groups = self.find_near_duplicates(assets, threshold)

        return exact_groups + near_groups
