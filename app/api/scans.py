from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..storage.database import DatabaseManager
from ..services.scanner import ScannerService
from ..services.image_fingerprint import ImageFingerprintService
from ..services.duplicate_detector import DuplicateDetectionService

router = APIRouter(prefix="/api/v1", tags=["scans"])

db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager("workspace/screenshot-index.db")
        db_manager.create_tables()
    return db_manager


class ScanRequest(BaseModel):
    root_path: str
    allowed_extensions: Optional[List[str]] = None


class ScanResponse(BaseModel):
    scan_id: str
    root_path: str
    status: str
    total_files: int
    error_count: int


class ScanStatusResponse(BaseModel):
    scan_id: str
    root_path: str
    status: str
    total_files: int
    error_count: int
    error_list: str
    started_at: str
    completed_at: Optional[str]


class AssetResponse(BaseModel):
    asset_id: str
    path: str
    filename: str
    extension: str
    sha256: str
    phash: Optional[str]
    size: int
    width: Optional[int]
    height: Optional[int]


class AssetListResponse(BaseModel):
    total: int
    items: List[AssetResponse]


@router.post("/scans", response_model=ScanResponse)
async def create_scan(request: ScanRequest) -> ScanResponse:
    """提交目录扫描任务"""
    db = get_db_manager().get_session()
    try:
        scanner = ScannerService(db)
        scan_run = scanner.scan_directory(
            root_path=request.root_path,
            allowed_extensions=request.allowed_extensions,
        )

        fingerprint_service = ImageFingerprintService(
            thumbnail_dir=Path("workspace/thumbnails")
        )

        assets = scanner.get_assets_by_scan_run(scan_run.id)
        for asset in assets:
            file_path = Path(asset.path)
            if file_path.exists():
                fp = fingerprint_service.compute_fingerprint(file_path)
                asset.sha256 = fp["sha256"]
                asset.phash = fp["phash"]
                asset.width = fp["width"]
                asset.height = fp["height"]

        db.commit()

        detector = DuplicateDetectionService(db)
        detector.detect_exact_duplicates(scan_run.id)
        detector.detect_near_duplicates(scan_run.id)

        return ScanResponse(
            scan_id=scan_run.id,
            root_path=str(scan_run.root_path),
            status=scan_run.status.value,
            total_files=scan_run.total_files,
            error_count=scan_run.error_count,
        )
    finally:
        db.close()


@router.get("/scans/{scan_id}", response_model=ScanStatusResponse)
async def get_scan_status(scan_id: str) -> ScanStatusResponse:
    """查询扫描进度与错误"""
    db = get_db_manager().get_session()
    try:
        scanner = ScannerService(db)
        scan_run = scanner.get_scan_run(scan_id)
        if not scan_run:
            raise HTTPException(status_code=404, detail="扫描任务不存在")

        return ScanStatusResponse(
            scan_id=scan_run.id,
            root_path=str(scan_run.root_path),
            status=scan_run.status.value,
            total_files=scan_run.total_files,
            error_count=scan_run.error_count,
            error_list=scan_run.error_list,
            started_at=scan_run.started_at.isoformat(),
            completed_at=scan_run.completed_at.isoformat()
            if scan_run.completed_at
            else None,
        )
    finally:
        db.close()


@router.get("/assets", response_model=AssetListResponse)
async def list_assets(
    scan_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> AssetListResponse:
    """查询索引资产"""
    db = get_db_manager().get_session()
    try:
        scanner = ScannerService(db)
        assets = scanner.get_assets_by_scan_run(scan_id, limit=limit, offset=offset)
        total = scanner.count_assets_by_scan_run(scan_id)

        items = [
            AssetResponse(
                asset_id=asset.id,
                path=asset.path,
                filename=asset.filename,
                extension=asset.extension,
                sha256=asset.sha256,
                phash=asset.phash,
                size=asset.size,
                width=asset.width,
                height=asset.height,
            )
            for asset in assets
        ]

        return AssetListResponse(total=total, items=items)
    finally:
        db.close()
