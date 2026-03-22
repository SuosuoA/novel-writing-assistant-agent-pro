"""
数据库连接池模块

V1.0版本
创建日期: 2026-03-21

特性：
- SQLite连接池（WAL模式）
- 线程安全
- 连接自动回收
"""

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
import queue


@dataclass
class ConnectionInfo:
    """连接信息"""
    connection: sqlite3.Connection
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    in_use: bool = False


class DatabasePool:
    """
    SQLite数据库连接池
    
    特性：
    - WAL模式支持
    - 连接复用
    - 线程安全
    - 自动回收
    - P0-3修复：连接使用超时保护
    - P0-3修复：优雅关闭机制
    
    用法:
        pool = DatabasePool("app.db", pool_size=5)
        
        # 上下文管理器
        with pool.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
        
        # 直接执行
        results = pool.execute("SELECT * FROM users WHERE id = ?", (1,))
    """
    
    # P0-3修复：默认最大连接使用时间（5分钟）
    DEFAULT_MAX_CONNECTION_TIME = 300.0
    
    def __init__(
        self,
        db_path: str = ":memory:",
        pool_size: int = 5,
        timeout: float = 30.0,
        wal_mode: bool = True,
        foreign_keys: bool = True,
        max_connection_time: float = None,
    ):
        """
        初始化数据库连接池
        
        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小
            timeout: 获取连接超时时间
            wal_mode: 是否启用WAL模式
            foreign_keys: 是否启用外键约束
            max_connection_time: 连接最大使用时间（秒），超时强制回收
        """
        self._db_path = db_path
        self._pool_size = pool_size
        self._timeout = timeout
        self._wal_mode = wal_mode
        self._foreign_keys = foreign_keys
        # P0-3修复：连接使用超时配置
        self._max_connection_time = max_connection_time or self.DEFAULT_MAX_CONNECTION_TIME
        
        self._pool: List[ConnectionInfo] = []
        self._lock = threading.RLock()
        self._available = threading.Condition(self._lock)
        # P0-3修复：关闭状态标记
        self._closed = False
        
        # 初始化连接池
        self._initialize_pool()
    
    def _initialize_pool(self) -> None:
        """初始化连接池"""
        for _ in range(self._pool_size):
            conn = self._create_connection()
            self._pool.append(ConnectionInfo(connection=conn))
    
    def _create_connection(self) -> sqlite3.Connection:
        """创建新连接"""
        # 确保目录存在
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(
            self._db_path,
            timeout=self._timeout,
            check_same_thread=False,
        )
        
        # 启用WAL模式
        if self._wal_mode:
            conn.execute("PRAGMA journal_mode=WAL")
        
        # 启用外键约束
        if self._foreign_keys:
            conn.execute("PRAGMA foreign_keys=ON")
        
        # 设置row_factory
        conn.row_factory = sqlite3.Row
        
        return conn
    
    def _get_connection(self) -> ConnectionInfo:
        """
        获取连接（内部方法）
        
        P0-3修复：添加连接使用超时保护，强制回收长时间占用的连接
        """
        with self._available:
            # P0-3修复：检查连接池是否已关闭
            if self._closed:
                raise RuntimeError("Database pool is closed")
            
            # 等待可用连接
            start_time = time.time()
            while True:
                # 查找空闲连接（含超时回收检查）
                for conn_info in self._pool:
                    # P0-3修复：检查连接是否超时被强制回收
                    if conn_info.in_use:
                        elapsed = (datetime.now() - conn_info.last_used).total_seconds()
                        if elapsed > self._max_connection_time:
                            # 强制回收超时连接
                            import logging
                            logging.warning(
                                f"Connection in use timeout, force reclaim: {elapsed:.1f}s"
                            )
                            conn_info.in_use = False
                    
                    if not conn_info.in_use:
                        conn_info.in_use = True
                        conn_info.last_used = datetime.now()
                        return conn_info
                
                # 检查超时
                elapsed = time.time() - start_time
                if elapsed >= self._timeout:
                    raise TimeoutError(
                        f"Failed to get database connection within {self._timeout}s"
                    )
                
                # 等待
                self._available.wait(self._timeout - elapsed)
    
    def _return_connection(self, conn_info: ConnectionInfo) -> None:
        """归还连接"""
        with self._available:
            conn_info.in_use = False
            self._available.notify()
    
    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        获取连接（上下文管理器）
        
        Yields:
            数据库连接
        """
        conn_info = self._get_connection()
        try:
            yield conn_info.connection
        finally:
            self._return_connection(conn_info)
    
    def execute(
        self,
        query: str,
        params: Tuple = (),
        commit: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        执行SQL查询
        
        Args:
            query: SQL语句
            params: 参数
            commit: 是否自动提交
        
        Returns:
            查询结果（字典列表）
        """
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if commit and not query.strip().upper().startswith("SELECT"):
                conn.commit()
            
            results = [dict(row) for row in cursor.fetchall()]
            return results
    
    def executemany(
        self,
        query: str,
        params_list: List[Tuple],
        commit: bool = True,
    ) -> int:
        """
        批量执行SQL
        
        Args:
            query: SQL语句
            params_list: 参数列表
            commit: 是否自动提交
        
        Returns:
            影响的行数
        """
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            
            if commit:
                conn.commit()
            
            return cursor.rowcount
    
    def execute_script(self, script: str) -> None:
        """
        执行SQL脚本
        
        Args:
            script: SQL脚本
        """
        with self.connection() as conn:
            conn.executescript(script)
            conn.commit()
    
    def table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        result = self.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return len(result) > 0
    
    def create_table(
        self,
        table_name: str,
        columns: Dict[str, str],
        if_not_exists: bool = True,
    ) -> None:
        """
        创建表
        
        Args:
            table_name: 表名
            columns: 列定义 {"name": "TEXT NOT NULL", ...}
            if_not_exists: 是否添加IF NOT EXISTS
        """
        column_defs = ", ".join(
            f"{name} {definition}" for name, definition in columns.items()
        )
        
        exists_clause = "IF NOT EXISTS" if if_not_exists else ""
        query = f"CREATE TABLE {exists_clause} {table_name} ({column_defs})"
        
        self.execute(query)
    
    def close(self, timeout: float = 5.0) -> None:
        """
        优雅关闭所有连接
        
        P0-3修复：等待使用中的连接归还后再关闭
        
        Args:
            timeout: 等待超时时间（秒）
        """
        import logging
        
        with self._lock:
            # P0-3修复：标记为已关闭，阻止新连接获取
            self._closed = True
            
            # P0-3修复：等待所有连接归还
            start_time = time.time()
            while any(c.in_use for c in self._pool):
                if time.time() - start_time > timeout:
                    in_use_count = sum(1 for c in self._pool if c.in_use)
                    logging.warning(
                        f"Close timeout, forcing close {in_use_count} connections in use"
                    )
                    break
                time.sleep(0.1)
            
            # 关闭所有连接
            closed_count = 0
            for conn_info in self._pool:
                try:
                    conn_info.connection.close()
                    closed_count += 1
                except Exception as e:
                    logging.warning(f"Error closing connection: {e}")
            
            self._pool.clear()
            logging.info(f"Database pool closed ({closed_count} connections)")
    
    def is_closed(self) -> bool:
        """P0-3修复：检查连接池是否已关闭"""
        with self._lock:
            return self._closed
    
    def get_pool_status(self) -> Dict[str, Any]:
        """获取连接池状态"""
        with self._lock:
            total = len(self._pool)
            in_use = sum(1 for c in self._pool if c.in_use)
            
            return {
                "db_path": self._db_path,
                "pool_size": self._pool_size,
                "total_connections": total,
                "in_use": in_use,
                "available": total - in_use,
            }


# 全局数据库池
_db_pool: Optional[DatabasePool] = None
_db_lock = threading.Lock()


def init_database(
    db_path: str = ":memory:",
    pool_size: int = 5,
    **kwargs
) -> DatabasePool:
    """
    初始化全局数据库池
    
    Args:
        db_path: 数据库路径
        pool_size: 连接池大小
        **kwargs: 其他参数
    
    Returns:
        DatabasePool实例
    """
    global _db_pool
    with _db_lock:
        if _db_pool is not None:
            _db_pool.close()
        _db_pool = DatabasePool(db_path, pool_size=pool_size, **kwargs)
        return _db_pool


def get_database_pool() -> DatabasePool:
    """获取全局数据库池"""
    global _db_pool
    if _db_pool is None:
        with _db_lock:
            if _db_pool is None:
                _db_pool = DatabasePool()
    return _db_pool
