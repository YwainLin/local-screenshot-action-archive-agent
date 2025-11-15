"""全文搜索服务"""

import logging
from datetime import datetime
from typing import Optional

from app.storage.database import DatabaseManager
from app.storage.models import Asset, Extraction, OcrResult

logger = logging.getLogger(__name__)


class SearchService:
    """全文搜索服务"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def init_fts_index(self) -> None:
        """初始化 FTS5 全文搜索索引"""
        # FTS5 索引已通过 migrations 创建
        pass

    def index_ocr_result(self, ocr_result: OcrResult) -> None:
        """将 OCR 结果添加到 FTS 索引

        Args:
            ocr_result: OCR 结果模型
        """
        # FTS 索引已通过 content sync 自动维护
        pass

    def remove_from_fts_index(self, asset_id: str) -> None:
        """从 FTS 索引中移除资产

        Args:
            asset_id: 资产 ID
        """
        # FTS 索引已通过 content sync 自动维护
        pass

    def search_keyword(
        self,
        keyword: str,
        limit: int = 50,
    ) -> list[dict]:
        """关键词搜索

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            搜索结果列表，包含 asset_id, text, rank
        """
        # 使用 LIKE 搜索
        rows = self.db_manager.fetchall(
            """
            SELECT asset_id, text, 0 as rank
            FROM ocr_result
            WHERE text LIKE ?
            LIMIT ?
            """,
            (f"%{keyword}%", limit),
        )

        return [
            {
                "asset_id": row["asset_id"],
                "text": row["text"],
                "rank": row["rank"],
            }
            for row in rows
        ]

    def search_by_date(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """按日期搜索

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            limit: 返回数量限制

        Returns:
            搜索结果列表
        """
        conditions = []
        params = []

        if start_date:
            conditions.append("e.value >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("e.value <= ?")
            params.append(end_date)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        rows = self.db_manager.fetchall(
            f"""
            SELECT DISTINCT
                a.id as asset_id,
                a.path,
                a.filename,
                e.value as date_value,
                e.evidence_span
            FROM asset a
            JOIN extraction e ON a.id = e.asset_id
            WHERE e.kind = 'date' AND {where_clause}
            ORDER BY e.value DESC
            LIMIT ?
            """,
            (*params, limit),
        )

        return [
            {
                "asset_id": row["asset_id"],
                "path": row["path"],
                "filename": row["filename"],
                "date_value": row["date_value"],
                "evidence": row["evidence_span"],
            }
            for row in rows
        ]

    def search_by_extraction_kind(
        self,
        kind: str,
        limit: int = 50,
    ) -> list[dict]:
        """按提取实体类型搜索

        Args:
            kind: 实体类型 (date/url/amount/action_phrase)
            limit: 返回数量限制

        Returns:
            搜索结果列表
        """
        rows = self.db_manager.fetchall(
            """
            SELECT DISTINCT
                a.id as asset_id,
                a.path,
                a.filename,
                e.value,
                e.evidence_span,
                e.confidence
            FROM asset a
            JOIN extraction e ON a.id = e.asset_id
            WHERE e.kind = ?
            ORDER BY e.confidence DESC
            LIMIT ?
            """,
            (kind, limit),
        )

        return [
            {
                "asset_id": row["asset_id"],
                "path": row["path"],
                "filename": row["filename"],
                "value": row["value"],
                "evidence": row["evidence_span"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]

    def search_by_asset(
        self,
        asset_id: str,
    ) -> dict:
        """获取资产的完整信息

        Args:
            asset_id: 资产 ID

        Returns:
            资产信息字典，包含 OCR 结果和提取实体
        """
        # 获取资产信息
        asset_row = self.db_manager.fetchone(
            "SELECT * FROM asset WHERE id = ?",
            (asset_id,),
        )
        if not asset_row:
            return {}

        # 获取 OCR 结果
        ocr_rows = self.db_manager.fetchall(
            "SELECT * FROM ocr_result WHERE asset_id = ?",
            (asset_id,),
        )

        # 获取提取实体
        extraction_rows = self.db_manager.fetchall(
            "SELECT * FROM extraction WHERE asset_id = ?",
            (asset_id,),
        )

        # 获取归档建议
        proposal_rows = self.db_manager.fetchall(
            "SELECT * FROM archive_proposal WHERE asset_id = ?",
            (asset_id,),
        )

        return {
            "asset": {
                "id": asset_row["id"],
                "path": asset_row["path"],
                "filename": asset_row["filename"],
                "sha256": asset_row["sha256"],
                "phash": asset_row["phash"],
                "size": asset_row["size"],
                "mtime": asset_row["mtime"],
                "width": asset_row["width"],
                "height": asset_row["height"],
            },
            "ocr_results": [
                {
                    "id": row["id"],
                    "engine": row["engine"],
                    "language": row["language"],
                    "text": row["text"],
                    "confidence": row["confidence"],
                }
                for row in ocr_rows
            ],
            "extractions": [
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "value": row["value"],
                    "value_masked": row["value_masked"],
                    "evidence_span": row["evidence_span"],
                    "confidence": row["confidence"],
                    "is_sensitive": row["is_sensitive"],
                }
                for row in extraction_rows
            ],
            "proposals": [
                {
                    "id": row["id"],
                    "action": row["action"],
                    "target_category": row["target_category"],
                    "confidence": row["confidence"],
                    "status": row["status"],
                }
                for row in proposal_rows
            ],
        }

    def search_combined(
        self,
        keyword: Optional[str] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        extraction_kind: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """组合搜索

        Args:
            keyword: 关键词
            date_start: 开始日期
            date_end: 结束日期
            extraction_kind: 提取实体类型
            limit: 返回数量限制

        Returns:
            搜索结果列表
        """
        conditions = []
        params = []

        if keyword:
            conditions.append(
                """
                a.id IN (
                    SELECT asset_id FROM ocr_result
                    WHERE text LIKE ?
                    UNION
                    SELECT asset_id FROM extraction
                    WHERE value LIKE ? OR evidence_span LIKE ?
                )
            """
            )
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

        if date_start or date_end:
            date_conditions = ["kind = 'date'"]
            if date_start:
                date_conditions.append("value >= ?")
                params.append(date_start)
            if date_end:
                date_conditions.append("value <= ?")
                params.append(date_end)

            conditions.append(
                f"""
                a.id IN (
                    SELECT asset_id FROM extraction
                    WHERE {' AND '.join(date_conditions)}
                )
            """
            )

        if extraction_kind:
            conditions.append(
                """
                a.id IN (
                    SELECT asset_id FROM extraction
                    WHERE kind = ?
                )
            """
            )
            params.append(extraction_kind)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        rows = self.db_manager.fetchall(
            f"""
            SELECT DISTINCT
                a.id as asset_id,
                a.path,
                a.filename,
                a.size,
                a.mtime
            FROM asset a
            WHERE {where_clause}
            ORDER BY a.mtime DESC
            LIMIT ?
            """,
            (*params, limit),
        )

        return [
            {
                "asset_id": row["asset_id"],
                "path": row["path"],
                "filename": row["filename"],
                "size": row["size"],
                "mtime": row["mtime"],
            }
            for row in rows
        ]
