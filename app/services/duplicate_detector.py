from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from ..storage.models import Asset, DuplicateGroup, DuplicateGroupMember, DuplicateKind
from .image_fingerprint import hash_distance


class DuplicateDetectionService:
    """重复检测服务"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def detect_exact_duplicates(self, scan_run_id: str) -> List[DuplicateGroup]:
        """检测完全重复（SHA-256 相同）"""
        assets = (
            self.db.query(Asset)
            .filter(Asset.scan_run_id == scan_run_id, Asset.sha256 != "")
            .all()
        )

        sha256_groups: Dict[str, List[Asset]] = defaultdict(list)
        for asset in assets:
            sha256_groups[asset.sha256].append(asset)

        groups = []
        for sha256, group_assets in sha256_groups.items():
            if len(group_assets) < 2:
                continue

            group = DuplicateGroup(
                id=str(uuid4()),
                kind=DuplicateKind.EXACT,
                representative_asset_id=group_assets[0].id,
                distance=0,
            )
            self.db.add(group)
            self.db.flush()

            for asset in group_assets:
                member = DuplicateGroupMember(
                    group_id=group.id,
                    asset_id=asset.id,
                )
                self.db.add(member)

            groups.append(group)

        self.db.commit()
        return groups

    def detect_near_duplicates(
        self, scan_run_id: str, threshold: int = 10
    ) -> List[DuplicateGroup]:
        """检测近似重复（pHash 距离小于阈值）"""
        assets = (
            self.db.query(Asset)
            .filter(
                Asset.scan_run_id == scan_run_id,
                Asset.phash.isnot(None),
                Asset.phash != "",
            )
            .all()
        )

        groups = []
        processed = set()

        for i, asset_a in enumerate(assets):
            if asset_a.id in processed:
                continue

            similar_assets = [asset_a]
            for j in range(i + 1, len(assets)):
                asset_b = assets[j]
                if asset_b.id in processed:
                    continue

                distance = hash_distance(asset_a.phash, asset_b.phash)
                if 0 < distance < threshold:
                    similar_assets.append(asset_b)
                    processed.add(asset_b.id)

            if len(similar_assets) < 2:
                continue

            group = DuplicateGroup(
                id=str(uuid4()),
                kind=DuplicateKind.NEAR,
                representative_asset_id=similar_assets[0].id,
                distance=threshold,
            )
            self.db.add(group)
            self.db.flush()

            for asset in similar_assets:
                member = DuplicateGroupMember(
                    group_id=group.id,
                    asset_id=asset.id,
                )
                self.db.add(member)
                processed.add(asset.id)

            groups.append(group)

        self.db.commit()
        return groups

    def get_duplicate_groups(
        self, scan_run_id: str, kind: Optional[DuplicateKind] = None
    ) -> List[DuplicateGroup]:
        """获取重复组列表"""
        query = (
            self.db.query(DuplicateGroup)
            .join(DuplicateGroupMember)
            .join(Asset)
            .filter(Asset.scan_run_id == scan_run_id)
        )

        if kind:
            query = query.filter(DuplicateGroup.kind == kind)

        return query.all()

    def get_group_assets(self, group_id: str) -> List[Asset]:
        """获取重复组中的所有资产"""
        return (
            self.db.query(Asset)
            .join(DuplicateGroupMember)
            .filter(DuplicateGroupMember.group_id == group_id)
            .all()
        )

    def count_groups_by_type(self, scan_run_id: str) -> Dict[str, int]:
        """统计各类型重复组数量"""
        exact_count = (
            self.db.query(DuplicateGroup)
            .join(DuplicateGroupMember)
            .join(Asset)
            .filter(
                Asset.scan_run_id == scan_run_id,
                DuplicateGroup.kind == DuplicateKind.EXACT,
            )
            .distinct()
            .count()
        )

        near_count = (
            self.db.query(DuplicateGroup)
            .join(DuplicateGroupMember)
            .join(Asset)
            .filter(
                Asset.scan_run_id == scan_run_id,
                DuplicateGroup.kind == DuplicateKind.NEAR,
            )
            .distinct()
            .count()
        )

        return {"exact": exact_count, "near": near_count}
