from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..storage.database import DatabaseManager
from ..services.index_store import IndexStore

router = APIRouter(prefix="/api/v1", tags=["search"])

db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager("workspace/screenshot-index.db")
        db_manager.create_tables()
    return db_manager


class SearchRequest(BaseModel):
    query: str
    kind_filter: Optional[str] = None
    limit: int = 50
    offset: int = 0


class SearchResultItem(BaseModel):
    asset_id: str
    filename: str
    path: str
    rank: float


class ExtractionSearchResultItem(BaseModel):
    extraction_id: str
    asset_id: str
    kind: str
    value_masked: str
    evidence_span: str
    rank: float


class SearchResponse(BaseModel):
    total: int
    items: List[SearchResultItem]


class ExtractionSearchResponse(BaseModel):
    total: int
    items: List[ExtractionSearchResultItem]


class ExtractionListResponse(BaseModel):
    asset_id: str
    extractions: List[Dict]


@router.get("/search", response_model=SearchResponse)
async def search_assets(
    q: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SearchResponse:
    """全文搜索资产"""
    db = get_db_manager().get_session()
    try:
        index_store = IndexStore(db)
        results = index_store.search_assets(q, limit=limit, offset=offset)
        total = index_store.count_search_results(q)

        items = [
            SearchResultItem(
                asset_id=r["asset_id"],
                filename=r["filename"],
                path=r["path"],
                rank=r["rank"],
            )
            for r in results
        ]

        return SearchResponse(total=total, items=items)
    finally:
        db.close()


@router.get("/search/extractions", response_model=ExtractionSearchResponse)
async def search_extractions(
    q: str,
    kind: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ExtractionSearchResponse:
    """搜索提取结果"""
    db = get_db_manager().get_session()
    try:
        index_store = IndexStore(db)
        results = index_store.search_extractions(
            q, kind_filter=kind, limit=limit, offset=offset
        )

        items = [
            ExtractionSearchResultItem(
                extraction_id=r["extraction_id"],
                asset_id=r["asset_id"],
                kind=r["kind"],
                value_masked=r["value_masked"],
                evidence_span=r["evidence_span"],
                rank=r["rank"],
            )
            for r in results
        ]

        return ExtractionSearchResponse(total=len(items), items=items)
    finally:
        db.close()


@router.get("/extractions/{asset_id}", response_model=ExtractionListResponse)
async def get_asset_extractions(asset_id: str) -> ExtractionListResponse:
    """获取资产的提取结果"""
    db = get_db_manager().get_session()
    try:
        index_store = IndexStore(db)
        extractions = index_store.get_extractions_by_asset(asset_id)

        return ExtractionListResponse(
            asset_id=asset_id,
            extractions=extractions,
        )
    finally:
        db.close()
