"""搜索服务单元测试"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from app.services.search import SearchService
from app.storage.database import DatabaseManager
from app.storage.migrations import run_migrations


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_manager(temp_dir):
    """创建数据库管理器"""
    db_path = temp_dir / "test.db"
    manager = DatabaseManager(str(db_path))
    run_migrations(manager)
    yield manager
    manager.close()


@pytest.fixture
def search_service(db_manager):
    """创建搜索服务实例"""
    return SearchService(db_manager)


@pytest.fixture
def populated_db(db_manager):
    """填充测试数据"""
    # 插入扫描任务
    db_manager.execute(
        "INSERT INTO scan_run (id, root_path, status) VALUES (?, ?, ?)",
        ("scan-1", "/tmp/screenshots", "completed"),
    )

    # 插入资产
    assets = [
        ("asset-1", "scan-1", "/tmp/screenshots/test1.png", "test1.png", 1024),
        ("asset-2", "scan-1", "/tmp/screenshots/test2.png", "test2.png", 2048),
        ("asset-3", "scan-1", "/tmp/screenshots/test3.png", "test3.png", 512),
    ]
    for asset in assets:
        db_manager.execute(
            """
            INSERT INTO asset (id, scan_run_id, path, filename, size, mtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (*asset, datetime.now().isoformat()),
        )

    # 插入 OCR 结果
    ocr_results = [
        ("ocr-1", "asset-1", "test", "ch", "这是一张订单截图，订单号 12345", 0.9),
        ("ocr-2", "asset-2", "test", "ch", "快递已发货，预计明天送达", 0.85),
        ("ocr-3", "asset-3", "test", "ch", "商品价格 ¥199.00，截止日期 2024-01-15", 0.88),
    ]
    for ocr in ocr_results:
        db_manager.execute(
            """
            INSERT INTO ocr_result (id, asset_id, engine, language, text, confidence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ocr,
        )

    # 插入提取实体
    extractions = [
        ("ext-1", "asset-1", "date", "2024-01-15", "2024-01-15", "截止日期 2024-01-15", 0.9),
        ("ext-2", "asset-1", "action_phrase", "订单号 12345", "订单号 12345", "订单号 12345", 0.85),
        ("ext-3", "asset-3", "amount", "¥199.00", "¥199.00", "商品价格 ¥199.00", 0.9),
        ("ext-4", "asset-3", "date", "2024-01-15", "2024-01-15", "截止日期 2024-01-15", 0.9),
    ]
    for ext in extractions:
        db_manager.execute(
            """
            INSERT INTO extraction (id, asset_id, kind, value, value_masked, evidence_span, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ext,
        )

    return db_manager


class TestSearchService:
    """搜索服务测试"""

    def test_init_fts_index(self, search_service):
        """测试初始化 FTS 索引"""
        search_service.init_fts_index()

        # 验证表已创建
        result = search_service.db_manager.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ocr_fts'"
        )
        assert result is not None

    def test_index_ocr_result(self, search_service, populated_db):
        """测试索引 OCR 结果"""
        search_service.init_fts_index()

        # 获取 OCR 结果
        ocr_row = populated_db.fetchone(
            "SELECT * FROM ocr_result WHERE id = ?", ("ocr-1",)
        )

        from app.storage.models import OcrResult

        ocr_result = OcrResult(
            id=ocr_row["id"],
            asset_id=ocr_row["asset_id"],
            engine=ocr_row["engine"],
            language=ocr_row["language"],
            text=ocr_row["text"],
            confidence=ocr_row["confidence"],
        )

        search_service.index_ocr_result(ocr_result)

        # 验证索引已创建
        fts_row = populated_db.fetchone(
            "SELECT * FROM ocr_fts WHERE asset_id = ?", ("asset-1",)
        )
        assert fts_row is not None

    def test_search_keyword(self, search_service, populated_db):
        """测试关键词搜索"""
        # 先索引 OCR 结果
        search_service.init_fts_index()
        ocr_rows = populated_db.fetchall("SELECT * FROM ocr_result")
        for row in ocr_rows:
            from app.storage.models import OcrResult

            ocr_result = OcrResult(
                id=row["id"],
                asset_id=row["asset_id"],
                engine=row["engine"],
                language=row["language"],
                text=row["text"],
                confidence=row["confidence"],
            )
            search_service.index_ocr_result(ocr_result)

        # 搜索
        results = search_service.search_keyword("订单")

        assert len(results) >= 1
        assert any(r["asset_id"] == "asset-1" for r in results)

    def test_search_keyword_fallback(self, search_service, populated_db):
        """测试关键词搜索回退"""
        # 不初始化 FTS，直接搜索
        results = search_service.search_keyword("订单")

        # 应该使用 LIKE 搜索
        assert len(results) >= 1

    def test_search_by_date(self, search_service, populated_db):
        """测试按日期搜索"""
        results = search_service.search_by_date(
            start_date="2024-01-01",
            end_date="2024-12-31",
        )

        assert len(results) >= 1
        assert any(r["asset_id"] in ["asset-1", "asset-3"] for r in results)

    def test_search_by_date_no_results(self, search_service, populated_db):
        """测试按日期搜索无结果"""
        results = search_service.search_by_date(
            start_date="2025-01-01",
            end_date="2025-12-31",
        )

        assert len(results) == 0

    def test_search_by_extraction_kind(self, search_service, populated_db):
        """测试按提取类型搜索"""
        results = search_service.search_by_extraction_kind("date")

        assert len(results) >= 2

    def test_search_by_asset(self, search_service, populated_db):
        """测试按资产搜索"""
        result = search_service.search_by_asset("asset-1")

        assert result["asset"]["id"] == "asset-1"
        assert len(result["ocr_results"]) >= 1
        assert len(result["extractions"]) >= 1

    def test_search_by_asset_not_found(self, search_service, populated_db):
        """测试搜索不存在的资产"""
        result = search_service.search_by_asset("nonexistent")

        assert result == {}

    def test_search_combined(self, search_service, populated_db):
        """测试组合搜索"""
        results = search_service.search_combined(
            keyword="订单",
            date_start="2024-01-01",
            date_end="2024-12-31",
        )

        assert len(results) >= 1

    def test_search_combined_no_filters(self, search_service, populated_db):
        """测试无过滤条件的组合搜索"""
        results = search_service.search_combined()

        assert len(results) == 3  # 所有资产
