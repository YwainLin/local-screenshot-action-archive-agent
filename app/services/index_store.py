from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..storage.models import Asset, Extraction, OcrResult


class IndexStore:
    """索引存储服务（基于 SQLite FTS5）"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def init_fts_tables(self) -> None:
        """初始化 FTS 虚拟表"""
        self.db.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS asset_fts USING fts5(
                    asset_id,
                    filename,
                    ocr_text,
                    extraction_text,
                    content='asset',
                    content_rowid='rowid'
                )
                """
            )
        )
        self.db.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS extraction_fts USING fts5(
                    extraction_id,
                    asset_id,
                    kind,
                    value_raw,
                    value_masked,
                    evidence_span,
                    content='extraction',
                    content_rowid='rowid'
                )
                """
            )
        )
        self.db.commit()

    def index_asset(self, asset_id: str) -> None:
        """索引单个资产"""
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return

        ocr_texts = []
        ocr_results = self.db.query(OcrResult).filter(OcrResult.asset_id == asset_id).all()
        for ocr in ocr_results:
            ocr_texts.append(ocr.text)

        extraction_texts = []
        extractions = self.db.query(Extraction).filter(Extraction.asset_id == asset_id).all()
        for ext in extractions:
            extraction_texts.append(f"{ext.kind}: {ext.value_raw}")

        self.db.execute(
            text(
                """
                INSERT OR REPLACE INTO asset_fts(asset_id, filename, ocr_text, extraction_text)
                VALUES (:asset_id, :filename, :ocr_text, :extraction_text)
                """
            ),
            {
                "asset_id": asset_id,
                "filename": asset.filename,
                "ocr_text": " ".join(ocr_texts),
                "extraction_text": " ".join(extraction_texts),
            },
        )
        self.db.commit()

    def index_extractions(self, asset_id: str) -> None:
        """索引资产的提取结果"""
        extractions = self.db.query(Extraction).filter(Extraction.asset_id == asset_id).all()

        for ext in extractions:
            self.db.execute(
                text(
                    """
                    INSERT OR REPLACE INTO extraction_fts(extraction_id, asset_id, kind, value_raw, value_masked, evidence_span)
                    VALUES (:extraction_id, :asset_id, :kind, :value_raw, :value_masked, :evidence_span)
                    """
                ),
                {
                    "extraction_id": ext.id,
                    "asset_id": asset_id,
                    "kind": ext.kind,
                    "value_raw": ext.value_raw,
                    "value_masked": ext.value_masked,
                    "evidence_span": ext.evidence_span or "",
                },
            )
        self.db.commit()

    def search_assets(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """全文搜索资产"""
        results = self.db.execute(
            text(
                """
                SELECT asset_id, rank
                FROM asset_fts
                WHERE asset_fts MATCH :query
                ORDER BY rank
                LIMIT :limit OFFSET :offset
                """
            ),
            {"query": query, "limit": limit, "offset": offset},
        ).fetchall()

        asset_ids = [r[0] for r in results]
        assets = self.db.query(Asset).filter(Asset.id.in_(asset_ids)).all()

        asset_map = {a.id: a for a in assets}
        return [
            {
                "asset_id": aid,
                "rank": rank,
                "path": asset_map[aid].path if aid in asset_map else "",
                "filename": asset_map[aid].filename if aid in asset_map else "",
            }
            for aid, rank in results
        ]

    def search_extractions(
        self,
        query: str,
        kind_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """搜索提取结果"""
        if kind_filter:
            results = self.db.execute(
                text(
                    """
                    SELECT extraction_id, asset_id, kind, value_masked, evidence_span, rank
                    FROM extraction_fts
                    WHERE extraction_fts MATCH :query AND kind = :kind
                    ORDER BY rank
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"query": query, "kind": kind_filter, "limit": limit, "offset": offset},
            ).fetchall()
        else:
            results = self.db.execute(
                text(
                    """
                    SELECT extraction_id, asset_id, kind, value_masked, evidence_span, rank
                    FROM extraction_fts
                    WHERE extraction_fts MATCH :query
                    ORDER BY rank
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"query": query, "limit": limit, "offset": offset},
            ).fetchall()

        return [
            {
                "extraction_id": r[0],
                "asset_id": r[1],
                "kind": r[2],
                "value_masked": r[3],
                "evidence_span": r[4],
                "rank": r[5],
            }
            for r in results
        ]

    def get_extractions_by_asset(self, asset_id: str) -> List[Dict]:
        """获取资产的所有提取结果"""
        extractions = self.db.query(Extraction).filter(Extraction.asset_id == asset_id).all()

        return [
            {
                "extraction_id": ext.id,
                "kind": ext.kind,
                "value_raw": ext.value_raw,
                "value_masked": ext.value_masked,
                "evidence_span": ext.evidence_span,
                "confidence": ext.confidence,
                "is_sensitive": ext.is_sensitive,
            }
            for ext in extractions
        ]

    def count_search_results(self, query: str) -> int:
        """统计搜索结果数量"""
        result = self.db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM asset_fts
                WHERE asset_fts MATCH :query
                """
            ),
            {"query": query},
        ).fetchone()
        return result[0] if result else 0


def get_index_store(db: Session) -> IndexStore:
    """获取索引存储服务实例"""
    return IndexStore(db)
