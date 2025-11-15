"""SQLite 数据库连接管理器"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional


class DatabaseManager:
    """SQLite 数据库管理器"""

    def __init__(self, db_path: str = "screenshot-index.db"):
        self.db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """建立数据库连接"""
        if self._connection is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(str(self.db_path))
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA foreign_keys=ON")
        return self._connection

    def close(self) -> None:
        """关闭数据库连接"""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """事务上下文管理器"""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL 语句"""
        conn = self.connect()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """批量执行 SQL 语句"""
        conn = self.connect()
        return conn.executemany(sql, params_list)

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """查询单条记录"""
        conn = self.connect()
        cursor = conn.execute(sql, params)
        return cursor.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """查询多条记录"""
        conn = self.connect()
        cursor = conn.execute(sql, params)
        return cursor.fetchall()

    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        result = self.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return result is not None

    def get_tables(self) -> list[str]:
        """获取所有表名"""
        rows = self.fetchall("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [row["name"] for row in rows]

    def __enter__(self) -> "DatabaseManager":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
