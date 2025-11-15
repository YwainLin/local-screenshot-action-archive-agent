"""数据库管理器单元测试"""

import tempfile
from pathlib import Path

import pytest

from app.storage.database import DatabaseManager
from app.storage.migrations import MigrationManager, run_migrations


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = DatabaseManager(str(db_path))
        yield manager
        manager.close()


@pytest.fixture
def migrated_db(temp_db):
    """创建已迁移的数据库"""
    run_migrations(temp_db)
    return temp_db


class TestDatabaseManager:
    """数据库管理器测试"""

    def test_connect(self, temp_db):
        """测试数据库连接"""
        conn = temp_db.connect()
        assert conn is not None

    def test_close(self, temp_db):
        """测试关闭数据库连接"""
        temp_db.connect()
        temp_db.close()
        assert temp_db._connection is None

    def test_execute(self, temp_db):
        """测试执行 SQL 语句"""
        temp_db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        temp_db.execute("INSERT INTO test (name) VALUES (?)", ("test",))
        result = temp_db.fetchone("SELECT * FROM test WHERE id=1")
        assert result is not None
        assert result["name"] == "test"

    def test_fetchall(self, temp_db):
        """测试查询多条记录"""
        temp_db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        temp_db.execute("INSERT INTO test (name) VALUES (?)", ("a",))
        temp_db.execute("INSERT INTO test (name) VALUES (?)", ("b",))
        results = temp_db.fetchall("SELECT * FROM test ORDER BY id")
        assert len(results) == 2

    def test_transaction_commit(self, temp_db):
        """测试事务提交"""
        temp_db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        with temp_db.transaction():
            temp_db.execute("INSERT INTO test (name) VALUES (?)", ("test",))
        result = temp_db.fetchone("SELECT * FROM test WHERE id=1")
        assert result is not None

    def test_transaction_rollback(self, temp_db):
        """测试事务回滚"""
        temp_db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        try:
            with temp_db.transaction():
                temp_db.execute("INSERT INTO test (name) VALUES (?)", ("test",))
                raise ValueError("Test error")
        except ValueError:
            pass
        result = temp_db.fetchone("SELECT * FROM test")
        assert result is None

    def test_table_exists(self, temp_db):
        """测试表存在检查"""
        assert temp_db.table_exists("sqlite_master") is True
        assert temp_db.table_exists("nonexistent") is False

    def test_get_tables(self, temp_db):
        """测试获取表列表"""
        temp_db.execute("CREATE TABLE test1 (id INTEGER)")
        temp_db.execute("CREATE TABLE test2 (id INTEGER)")
        tables = temp_db.get_tables()
        assert "test1" in tables
        assert "test2" in tables

    def test_context_manager(self, temp_db):
        """测试上下文管理器"""
        with temp_db:
            conn = temp_db.connect()
            assert conn is not None
        assert temp_db._connection is None


class TestMigrationManager:
    """迁移管理器测试"""

    def test_ensure_migrations_table(self, temp_db):
        """测试创建迁移记录表"""
        MigrationManager(temp_db)
        assert temp_db.table_exists("schema_migrations") is True

    def test_get_current_version(self, temp_db):
        """测试获取当前版本"""
        manager = MigrationManager(temp_db)
        version = manager.get_current_version()
        assert version == 0

    def test_get_applied_migrations(self, temp_db):
        """测试获取已应用迁移列表"""
        manager = MigrationManager(temp_db)
        migrations = manager.get_applied_migrations()
        assert len(migrations) == 0

    def test_apply_migration(self, temp_db):
        """测试应用迁移"""
        manager = MigrationManager(temp_db)
        manager.apply_migration(
            version=1,
            name="test_migration",
            sql="CREATE TABLE test (id INTEGER PRIMARY KEY)",
        )
        assert manager.get_current_version() == 1
        assert temp_db.table_exists("test") is True

    def test_apply_migration_idempotent(self, temp_db):
        """测试迁移幂等性"""
        manager = MigrationManager(temp_db)
        manager.apply_migration(
            version=1,
            name="test_migration",
            sql="CREATE TABLE test (id INTEGER PRIMARY KEY)",
        )
        # 再次应用同一版本
        manager.apply_migration(
            version=1,
            name="test_migration",
            sql="CREATE TABLE test2 (id INTEGER)",
        )
        assert manager.get_current_version() == 1
        assert temp_db.table_exists("test2") is False


class TestRunMigrations:
    """运行迁移测试"""

    def test_run_initial_migration(self, migrated_db):
        """测试运行初始迁移"""
        # 检查所有核心表是否创建
        expected_tables = [
            "scan_run",
            "asset",
            "duplicate_group",
            "duplicate_group_asset",
            "ocr_result",
            "extraction",
            "archive_proposal",
            "audit_event",
            "schema_migrations",
        ]
        tables = migrated_db.get_tables()
        for table in expected_tables:
            assert table in tables, f"Table {table} not found"

    def test_run_migrations_version(self, migrated_db):
        """测试迁移版本号"""
        manager = MigrationManager(migrated_db)
        version = manager.get_current_version()
        assert version == 1

    def test_run_migrations_idempotent(self, migrated_db):
        """测试迁移幂等性"""
        # 再次运行迁移
        run_migrations(migrated_db)
        manager = MigrationManager(migrated_db)
        version = manager.get_current_version()
        assert version == 1
