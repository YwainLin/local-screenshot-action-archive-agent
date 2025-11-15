"""数据库迁移管理"""

import sqlite3
from datetime import datetime
from typing import Optional

from app.storage.database import DatabaseManager


class MigrationManager:
    """数据库迁移管理器"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self._ensure_migrations_table()

    def _ensure_migrations_table(self) -> None:
        """确保迁移记录表存在"""
        self.db_manager.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db_manager.execute("PRAGMA user_version=0")

    def get_current_version(self) -> int:
        """获取当前数据库版本"""
        result = self.db_manager.fetchone("PRAGMA user_version")
        return result[0] if result else 0

    def get_applied_migrations(self) -> list[dict]:
        """获取已应用的迁移列表"""
        rows = self.db_manager.fetchall(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        )
        return [dict(row) for row in rows]

    def apply_migration(self, version: int, name: str, sql: str) -> None:
        """应用单个迁移"""
        current = self.get_current_version()
        if version <= current:
            return

        with self.db_manager.transaction():
            self.db_manager.execute(sql)
            self.db_manager.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (version, name),
            )
            self.db_manager.execute(f"PRAGMA user_version={version}")


def get_initial_migration() -> tuple[int, str, str]:
    """获取初始迁移：创建所有核心表"""
    return (
        1,
        "initial_schema",
        """
        -- 扫描任务表
        CREATE TABLE IF NOT EXISTS scan_run (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            root_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            total_files INTEGER DEFAULT 0,
            scanned_files INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            error_messages TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 图片资产表
        CREATE TABLE IF NOT EXISTS asset (
            id TEXT PRIMARY KEY,
            scan_run_id TEXT NOT NULL,
            path TEXT NOT NULL,
            filename TEXT NOT NULL,
            sha256 TEXT,
            phash TEXT,
            size INTEGER NOT NULL,
            mtime TIMESTAMP NOT NULL,
            width INTEGER,
            height INTEGER,
            thumbnail_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scan_run_id) REFERENCES scan_run(id) ON DELETE CASCADE
        );

        -- 重复组表
        CREATE TABLE IF NOT EXISTS duplicate_group (
            id TEXT PRIMARY KEY,
            scan_run_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('exact', 'near')),
            representative_asset_id TEXT NOT NULL,
            distance INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scan_run_id) REFERENCES scan_run(id) ON DELETE CASCADE,
            FOREIGN KEY (representative_asset_id) REFERENCES asset(id)
        );

        -- 重复组-资产关联表
        CREATE TABLE IF NOT EXISTS duplicate_group_asset (
            group_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            PRIMARY KEY (group_id, asset_id),
            FOREIGN KEY (group_id) REFERENCES duplicate_group(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE
        );

        -- OCR 结果表
        CREATE TABLE IF NOT EXISTS ocr_result (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            engine TEXT NOT NULL,
            engine_version TEXT DEFAULT '',
            language TEXT NOT NULL,
            text TEXT NOT NULL,
            confidence REAL DEFAULT 0.0,
            is_sensitive INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE
        );

        -- 提取实体表
        CREATE TABLE IF NOT EXISTS extraction (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            ocr_result_id TEXT,
            kind TEXT NOT NULL,
            value TEXT NOT NULL,
            value_masked TEXT NOT NULL,
            evidence_span TEXT NOT NULL,
            confidence REAL DEFAULT 0.0,
            is_sensitive INTEGER DEFAULT 0,
            source TEXT DEFAULT 'rule' CHECK (source IN ('rule', 'model_suggestion')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE,
            FOREIGN KEY (ocr_result_id) REFERENCES ocr_result(id) ON DELETE SET NULL
        );

        -- 归档建议表
        CREATE TABLE IF NOT EXISTS archive_proposal (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('keep', 'mark_pending', 'copy_to_category', 'merge_duplicate')),
            suggested_category TEXT,
            target_path TEXT,
            confidence REAL DEFAULT 0.0,
            rationale TEXT DEFAULT '',
            requires_approval INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'applied')),
            rejection_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE
        );

        -- 审计事件表
        CREATE TABLE IF NOT EXISTS audit_event (
            id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('copy', 'export', 'reject', 'error')),
            asset_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            target_path TEXT,
            before_hash TEXT,
            after_hash TEXT,
            success INTEGER DEFAULT 1,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (proposal_id) REFERENCES archive_proposal(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES asset(id) ON DELETE CASCADE
        );

        -- 创建索引
        CREATE INDEX IF NOT EXISTS idx_asset_scan_run ON asset(scan_run_id);
        CREATE INDEX IF NOT EXISTS idx_asset_sha256 ON asset(sha256);
        CREATE INDEX IF NOT EXISTS idx_asset_phash ON asset(phash);
        CREATE INDEX IF NOT EXISTS idx_duplicate_group_scan_run ON duplicate_group(scan_run_id);
        CREATE INDEX IF NOT EXISTS idx_ocr_result_asset ON ocr_result(asset_id);
        CREATE INDEX IF NOT EXISTS idx_extraction_asset ON extraction(asset_id);
        CREATE INDEX IF NOT EXISTS idx_extraction_kind ON extraction(kind);
        CREATE INDEX IF NOT EXISTS idx_archive_proposal_asset ON archive_proposal(asset_id);
        CREATE INDEX IF NOT EXISTS idx_archive_proposal_status ON archive_proposal(status);
        CREATE INDEX IF NOT EXISTS idx_audit_event_proposal ON audit_event(proposal_id);
        CREATE INDEX IF NOT EXISTS idx_audit_event_asset ON audit_event(asset_id);

        -- 创建 FTS5 全文搜索虚拟表（OCR 文本搜索）
        CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(
            asset_id UNINDEXED,
            text,
            content='ocr_result',
            content_rowid='rowid'
        );
        """,
    )


def run_migrations(db_manager: DatabaseManager) -> None:
    """运行所有待应用的迁移"""
    migration_manager = MigrationManager(db_manager)

    # 获取所有可用迁移
    migrations = [
        get_initial_migration(),
    ]

    # 按版本号排序
    migrations.sort(key=lambda x: x[0])

    # 应用迁移
    for version, name, sql in migrations:
        migration_manager.apply_migration(version, name, sql)
