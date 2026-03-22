"""
数据库持久化层 - SQLite + WAL模式

V1.0版本
创建日期：2026-03-21

特性：
- SQLite + WAL模式并发
- 连接池管理
- 数据库迁移
- Agent状态持久化
- 线程安全
"""

import sqlite3
import threading
import json
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type
from enum import Enum

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """数据库异常"""

    pass


class MigrationStatus(str, Enum):
    """迁移状态"""

    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"


class ConnectionPool:
    """
    SQLite连接池

    注意：SQLite的连接不能跨线程共享，因此使用线程本地存储
    """

    # P1-1修复：添加连接池大小限制常量
    DEFAULT_MAX_CONNECTIONS = 20
    MIN_CONNECTIONS = 1
    MAX_CONNECTIONS_LIMIT = 100  # 硬性上限

    def __init__(self, db_path: str, pool_size: int = 5, timeout: float = 30.0):
        """
        初始化连接池

        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小（实际是每个线程一个连接）
            timeout: 连接超时时间

        Raises:
            ValueError: pool_size超出允许范围
        """
        # P1-1修复：验证pool_size参数
        if not isinstance(pool_size, int) or pool_size < self.MIN_CONNECTIONS:
            raise ValueError(
                f"pool_size must be >= {self.MIN_CONNECTIONS}, got {pool_size}"
            )
        if pool_size > self.MAX_CONNECTIONS_LIMIT:
            raise ValueError(
                f"pool_size must be <= {self.MAX_CONNECTIONS_LIMIT}, got {pool_size}"
            )

        self._db_path = db_path
        self._pool_size = min(pool_size, self.DEFAULT_MAX_CONNECTIONS)
        self._timeout = timeout
        self._lock = threading.RLock()
        self._thread_local = threading.local()

        # 跟踪所有连接（用于正确关闭）
        self._all_connections: List[sqlite3.Connection] = []
        self._connections_lock = threading.Lock()

        # P1-1修复：连接计数器和信号量
        self._connection_count = 0
        self._connection_semaphore = threading.Semaphore(self._pool_size)

        # P0-3修复：连接使用超时和关闭标记
        self._max_connection_time = 300.0  # 单个连接最大使用时间（5分钟）
        self._connection_last_used: Dict[sqlite3.Connection, datetime] = {}
        self._closed = False  # 连接池关闭标记

        # 确保数据库目录存在
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self, timeout: Optional[float] = None) -> sqlite3.Connection:
        """
        获取当前线程的数据库连接

        Args:
            timeout: 获取连接的超时时间（秒），None表示使用默认超时

        Returns:
            SQLite连接对象

        Raises:
            TimeoutError: 无法在指定时间内获取连接（连接池已满）
            RuntimeError: 连接池已关闭
        """
        # P0-3修复：检查连接池是否已关闭
        if self._closed:
            raise RuntimeError("Connection pool is closed")

        # P1-1修复：使用信号量限制连接数
        acquire_timeout = timeout if timeout is not None else self._timeout
        if not self._connection_semaphore.acquire(timeout=acquire_timeout):
            raise TimeoutError(
                f"Connection pool exhausted. "
                f"Max connections: {self._pool_size}, "
                f"Current count: {self._connection_count}"
            )

        try:
            if (
                not hasattr(self._thread_local, "connection")
                or self._thread_local.connection is None
            ):
                conn = sqlite3.connect(
                    self._db_path, timeout=self._timeout, check_same_thread=False
                )

                # 启用WAL模式
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=-64000")  # 64MB缓存
                conn.execute("PRAGMA foreign_keys=ON")

                # 启用row_factory
                conn.row_factory = sqlite3.Row

                self._thread_local.connection = conn

                # 跟踪连接
                with self._connections_lock:
                    self._all_connections.append(conn)
                    self._connection_count += 1
                    self._connection_last_used[conn] = datetime.now()
                    logger.debug(
                        f"Connection created. "
                        f"Total: {self._connection_count}/{self._pool_size}"
                    )

            # P0-3修复：更新连接最后使用时间
            conn = self._thread_local.connection
            with self._connections_lock:
                self._connection_last_used[conn] = datetime.now()

            return conn
        except Exception:
            # 获取连接失败时释放信号量
            self._connection_semaphore.release()
            raise

    def close_all(self) -> None:
        """
        关闭所有连接（P0-3修复：优雅关闭）

        等待使用中的连接归还后再关闭。
        """
        # P0-3修复：设置关闭标记
        with self._connections_lock:
            if self._closed:
                logger.warning("Connection pool already closed")
                return
            self._closed = True

        # P0-3修复：等待所有连接归还（最多等待5秒）
        import time
        wait_timeout = 5.0
        start_time = time.time()

        while time.time() - start_time < wait_timeout:
            # 检查是否有连接在使用（通过信号量判断）
            available = self._connection_semaphore._value
            if available >= self._pool_size:
                break
            time.sleep(0.1)

        with self._connections_lock:
            # 关闭所有连接
            closed_count = 0
            for conn in self._all_connections:
                try:
                    conn.close()
                    closed_count += 1
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")

            self._all_connections.clear()
            self._connection_count = 0
            self._connection_last_used.clear()

            # P1-1修复：释放所有信号量
            for _ in range(self._pool_size):
                try:
                    self._connection_semaphore.release()
                except ValueError:
                    # 信号量已满，忽略
                    pass

        # 清理线程本地连接引用
        with self._lock:
            self._thread_local.connection = None

        logger.info(f"All database connections closed ({closed_count} connections)")

    def force_close_all(self) -> None:
        """
        强制关闭所有连接（P0-3修复：用于紧急情况）

        不等待使用中的连接归还，立即关闭。
        """
        self._closed = True

        with self._connections_lock:
            closed_count = 0
            for conn in self._all_connections:
                try:
                    conn.close()
                    closed_count += 1
                except Exception as e:
                    logger.warning(f"Error force closing connection: {e}")

            self._all_connections.clear()
            self._connection_count = 0
            self._connection_last_used.clear()

        with self._lock:
            self._thread_local.connection = None

        logger.warning(f"All database connections force closed ({closed_count} connections)")

    def get_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态（P1-1修复：新增监控接口）

        Returns:
            连接池状态信息
        """
        with self._connections_lock:
            return {
                "max_connections": self._pool_size,
                "current_count": self._connection_count,
                "available_slots": self._pool_size - self._connection_count,
                "db_path": str(self._db_path),
            }


class DatabaseMigration:
    """
    数据库迁移管理器
    """

    MIGRATIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS _migrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        applied_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'applied'
    )
    """

    def __init__(self, connection_pool: ConnectionPool):
        """
        初始化迁移管理器

        Args:
            connection_pool: 连接池实例
        """
        self._pool = connection_pool
        self._migrations: Dict[str, str] = {}

        # 初始化迁移表
        self._init_migrations_table()

    def _init_migrations_table(self) -> None:
        """初始化迁移记录表"""
        conn = self._pool.get_connection()
        conn.execute(self.MIGRATIONS_TABLE)
        conn.commit()

    def register_migration(self, name: str, sql: str) -> None:
        """
        注册迁移脚本（带安全验证）

        Args:
            name: 迁移名称（唯一标识）
            sql: SQL脚本

        Raises:
            ValueError: 迁移名称格式无效或SQL包含危险模式
        """
        import re

        # 1. 验证迁移名称格式（格式：001_create_table）
        if not re.match(r'^\d{3}_[a-z_]+$', name):
            raise ValueError(
                f"Invalid migration name: {name}. "
                f"Expected format: 'XXX_description' (e.g., '001_create_table')"
            )

        # 2. 检查危险SQL模式
        dangerous_patterns = [
            (r'DROP\s+TABLE', 'DROP TABLE'),
            (r'DELETE\s+FROM', 'DELETE FROM'),
            (r'TRUNCATE\s+TABLE', 'TRUNCATE TABLE'),
            (r'--.*$', 'SQL comment'),  # SQL注释可能隐藏恶意代码
        ]

        for pattern, pattern_name in dangerous_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                raise ValueError(
                    f"Migration '{name}' contains dangerous SQL pattern: {pattern_name}. "
                    f"Please use safe operations only."
                )

        self._migrations[name] = sql
        logger.info(f"Migration registered: {name}")

    def get_pending_migrations(self) -> List[str]:
        """
        获取待执行的迁移列表

        Returns:
            待执行的迁移名称列表
        """
        conn = self._pool.get_connection()
        cursor = conn.execute(
            "SELECT name FROM _migrations WHERE status = ?",
            (MigrationStatus.APPLIED.value,),
        )
        applied = {row["name"] for row in cursor.fetchall()}

        return [name for name in self._migrations.keys() if name not in applied]

    def apply_migration(self, name: str) -> bool:
        """
        应用单个迁移（带事务保护）

        Args:
            name: 迁移名称

        Returns:
            是否成功
        """
        if name not in self._migrations:
            logger.error(f"Migration not found: {name}")
            return False

        sql = self._migrations[name]
        conn = self._pool.get_connection()

        try:
            # 开始事务
            conn.execute("BEGIN TRANSACTION")

            # 拆分SQL语句并逐条执行（而不是executescript）
            statements = [s.strip() for s in sql.split(';') if s.strip()]

            for stmt in statements:
                conn.execute(stmt)

            # 记录迁移
            conn.execute(
                """
                INSERT INTO _migrations (name, applied_at, status)
                VALUES (?, ?, ?)
                """,
                (name, datetime.now().isoformat(), MigrationStatus.APPLIED.value),
            )

            # 提交事务
            conn.commit()
            logger.info(f"Migration applied successfully: {name}")
            return True

        except Exception as e:
            # 回滚事务
            conn.rollback()
            logger.error(f"Migration failed: {name}, error: {e}")

            # 记录失败状态
            try:
                conn.execute(
                    """
                    INSERT INTO _migrations (name, applied_at, status)
                    VALUES (?, ?, ?)
                    """,
                    (name, datetime.now().isoformat(), MigrationStatus.FAILED.value),
                )
                conn.commit()
            except Exception as record_error:
                logger.error(f"Failed to record migration failure: {record_error}")

            return False

    def apply_all(self) -> Dict[str, bool]:
        """
        应用所有待执行的迁移

        Returns:
            迁移结果 {migration_name: bool}
        """
        pending = self.get_pending_migrations()
        results = {}

        for name in pending:
            results[name] = self.apply_migration(name)

        return results


class AgentStateStore:
    """
    Agent状态持久化存储

    用于存储MasterAgent、专家Agent的状态和任务信息
    """

    CREATE_AGENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'idle',
        config TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """

    CREATE_TASKS_TABLE = """
    CREATE TABLE IF NOT EXISTS agent_tasks (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        task_type TEXT NOT NULL,
        priority INTEGER DEFAULT 2,
        status TEXT NOT NULL DEFAULT 'pending',
        input_data TEXT,
        output_data TEXT,
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        FOREIGN KEY (agent_id) REFERENCES agents(id)
    )
    """

    CREATE_TASK_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_tasks_agent_id ON agent_tasks(agent_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_status ON agent_tasks(status);
    CREATE INDEX IF NOT EXISTS idx_tasks_priority ON agent_tasks(priority);
    """

    def __init__(self, connection_pool: ConnectionPool):
        """
        初始化Agent状态存储

        Args:
            connection_pool: 连接池实例
        """
        self._pool = connection_pool
        self._migration = DatabaseMigration(connection_pool)

        # 注册迁移
        self._migration.register_migration(
            "001_create_agents", self.CREATE_AGENTS_TABLE
        )
        self._migration.register_migration("002_create_tasks", self.CREATE_TASKS_TABLE)
        self._migration.register_migration("003_create_indexes", self.CREATE_TASK_INDEX)

        # 应用迁移
        self._migration.apply_all()

    # =========================================================================
    # Agent操作
    # =========================================================================

    def save_agent(
        self,
        agent_id: str,
        agent_type: str,
        state: str = "idle",
        config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        保存或更新Agent状态

        Args:
            agent_id: Agent ID
            agent_type: Agent类型（master/thinker/optimizer/validator/planner）
            state: Agent状态（idle/running/error）
            config: Agent配置

        Returns:
            是否成功
        """
        conn = self._pool.get_connection()
        now = datetime.now().isoformat()

        try:
            conn.execute(
                """
                INSERT INTO agents (id, type, state, config, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state = excluded.state,
                    config = excluded.config,
                    updated_at = excluded.updated_at
                """,
                (
                    agent_id,
                    agent_type,
                    state,
                    json.dumps(config) if config else None,
                    now,
                    now,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save agent: {e}")
            conn.rollback()
            return False

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        获取Agent信息

        Args:
            agent_id: Agent ID

        Returns:
            Agent信息字典
        """
        conn = self._pool.get_connection()
        cursor = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = cursor.fetchone()

        if row:
            return {
                "id": row["id"],
                "type": row["type"],
                "state": row["state"],
                "config": json.loads(row["config"]) if row["config"] else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        return None

    def update_agent_state(self, agent_id: str, state: str) -> bool:
        """
        更新Agent状态

        Args:
            agent_id: Agent ID
            state: 新状态

        Returns:
            是否成功
        """
        conn = self._pool.get_connection()

        try:
            conn.execute(
                "UPDATE agents SET state = ?, updated_at = ? WHERE id = ?",
                (state, datetime.now().isoformat(), agent_id),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update agent state: {e}")
            conn.rollback()
            return False

    def delete_agent(self, agent_id: str) -> bool:
        """
        删除Agent

        Args:
            agent_id: Agent ID

        Returns:
            是否成功
        """
        conn = self._pool.get_connection()

        try:
            # 先删除关联任务
            conn.execute("DELETE FROM agent_tasks WHERE agent_id = ?", (agent_id,))
            conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete agent: {e}")
            conn.rollback()
            return False

    # =========================================================================
    # Task操作
    # =========================================================================

    def save_task(
        self,
        task_id: str,
        agent_id: str,
        task_type: str,
        priority: int = 2,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        保存任务

        Args:
            task_id: 任务ID
            agent_id: 执行Agent ID
            task_type: 任务类型
            priority: 优先级（0=Critical, 1=High, 2=Normal, 3=Low, 4=Background）
            input_data: 输入数据

        Returns:
            是否成功
        """
        conn = self._pool.get_connection()
        now = datetime.now().isoformat()

        try:
            conn.execute(
                """
                INSERT INTO agent_tasks 
                (id, agent_id, task_type, priority, status, input_data, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    task_id,
                    agent_id,
                    task_type,
                    priority,
                    json.dumps(input_data) if input_data else None,
                    now,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save task: {e}")
            conn.rollback()
            return False

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务信息

        Args:
            task_id: 任务ID

        Returns:
            任务信息字典
        """
        conn = self._pool.get_connection()
        cursor = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        if row:
            return self._row_to_task(row)
        return None

    def get_pending_tasks(
        self, agent_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取待执行任务列表（按优先级排序）

        Args:
            agent_id: Agent ID（可选，不指定则返回所有）
            limit: 最大返回数量

        Returns:
            任务列表
        """
        conn = self._pool.get_connection()

        if agent_id:
            cursor = conn.execute(
                """
                SELECT * FROM agent_tasks 
                WHERE agent_id = ? AND status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT ?
                """,
                (agent_id, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM agent_tasks 
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT ?
                """,
                (limit,),
            )

        return [self._row_to_task(row) for row in cursor.fetchall()]

    def update_task_status(
        self,
        task_id: str,
        status: str,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态（pending/running/completed/failed/cancelled）
            output_data: 输出数据
            error_message: 错误信息

        Returns:
            是否成功
        """
        conn = self._pool.get_connection()

        try:
            now = datetime.now().isoformat()

            if status == "running":
                conn.execute(
                    "UPDATE agent_tasks SET status = ?, started_at = ? WHERE id = ?",
                    (status, now, task_id),
                )
            elif status in ("completed", "failed", "cancelled"):
                conn.execute(
                    """
                    UPDATE agent_tasks 
                    SET status = ?, output_data = ?, error_message = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        json.dumps(output_data) if output_data else None,
                        error_message,
                        now,
                        task_id,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE agent_tasks SET status = ? WHERE id = ?", (status, task_id)
                )

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
            conn.rollback()
            return False

    def increment_retry_count(self, task_id: str) -> int:
        """
        增加重试计数

        Args:
            task_id: 任务ID

        Returns:
            新的重试计数
        """
        conn = self._pool.get_connection()

        try:
            conn.execute(
                "UPDATE agent_tasks SET retry_count = retry_count + 1 WHERE id = ?",
                (task_id,),
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT retry_count FROM agent_tasks WHERE id = ?", (task_id,)
            )
            row = cursor.fetchone()
            return row["retry_count"] if row else 0
        except Exception as e:
            logger.error(f"Failed to increment retry count: {e}")
            conn.rollback()
            return -1

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功
        """
        conn = self._pool.get_connection()

        try:
            conn.execute("DELETE FROM agent_tasks WHERE id = ?", (task_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete task: {e}")
            conn.rollback()
            return False

    def cleanup_old_tasks(self, days: int = 30) -> int:
        """
        清理旧任务

        Args:
            days: 保留天数

        Returns:
            删除的任务数量
        """
        conn = self._pool.get_connection()

        try:
            # SQLite日期计算
            cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
            cutoff_str = datetime.fromtimestamp(cutoff).isoformat()

            cursor = conn.execute(
                """
                DELETE FROM agent_tasks 
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND completed_at < ?
                """,
                (cutoff_str,),
            )
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to cleanup old tasks: {e}")
            conn.rollback()
            return 0

    def _row_to_task(self, row: sqlite3.Row) -> Dict[str, Any]:
        """将数据库行转换为任务字典"""
        return {
            "id": row["id"],
            "agent_id": row["agent_id"],
            "task_type": row["task_type"],
            "priority": row["priority"],
            "status": row["status"],
            "input_data": json.loads(row["input_data"]) if row["input_data"] else None,
            "output_data": (
                json.loads(row["output_data"]) if row["output_data"] else None
            ),
            "error_message": row["error_message"],
            "retry_count": row["retry_count"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }


class GenerationHistoryStore:
    """
    生成历史存储

    用于存储章节生成记录和验证评分
    """

    CREATE_GENERATIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS generations (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        chapter_id TEXT NOT NULL,
        chapter_title TEXT NOT NULL,
        content TEXT,
        word_count INTEGER DEFAULT 0,
        iteration_count INTEGER DEFAULT 0,
        scores TEXT,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        created_at TEXT NOT NULL,
        completed_at TEXT
    )
    """

    CREATE_GENERATION_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_generations_project ON generations(project_id);
    CREATE INDEX IF NOT EXISTS idx_generations_chapter ON generations(chapter_id);
    CREATE INDEX IF NOT EXISTS idx_generations_status ON generations(status);
    """

    def __init__(self, connection_pool: ConnectionPool):
        """
        初始化生成历史存储

        Args:
            connection_pool: 连接池实例
        """
        self._pool = connection_pool
        self._migration = DatabaseMigration(connection_pool)

        # 注册迁移
        self._migration.register_migration(
            "010_create_generations", self.CREATE_GENERATIONS_TABLE
        )
        self._migration.register_migration(
            "011_create_gen_indexes", self.CREATE_GENERATION_INDEX
        )

        # 应用迁移
        self._migration.apply_all()

    def save_generation(
        self,
        generation_id: str,
        project_id: str,
        chapter_id: str,
        chapter_title: str,
        content: Optional[str] = None,
        word_count: int = 0,
        iteration_count: int = 1,
        scores: Optional[Dict[str, float]] = None,
        status: str = "pending",
    ) -> bool:
        """
        保存生成记录

        Args:
            generation_id: 生成ID
            project_id: 项目ID
            chapter_id: 章节ID
            chapter_title: 章节标题
            content: 生成内容
            word_count: 字数
            iteration_count: 迭代次数
            scores: 评分
            status: 状态

        Returns:
            是否成功
        """
        conn = self._pool.get_connection()
        now = datetime.now().isoformat()

        try:
            conn.execute(
                """
                INSERT INTO generations 
                (id, project_id, chapter_id, chapter_title, content, word_count, 
                 iteration_count, scores, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generation_id,
                    project_id,
                    chapter_id,
                    chapter_title,
                    content,
                    word_count,
                    iteration_count,
                    json.dumps(scores) if scores else None,
                    status,
                    now,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save generation: {e}")
            conn.rollback()
            return False

    def update_generation(
        self,
        generation_id: str,
        content: Optional[str] = None,
        word_count: Optional[int] = None,
        iteration_count: Optional[int] = None,
        scores: Optional[Dict[str, float]] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        更新生成记录

        Returns:
            是否成功
        """
        conn = self._pool.get_connection()

        try:
            updates = []
            params = []

            if content is not None:
                updates.append("content = ?")
                params.append(content)
            if word_count is not None:
                updates.append("word_count = ?")
                params.append(word_count)
            if iteration_count is not None:
                updates.append("iteration_count = ?")
                params.append(iteration_count)
            if scores is not None:
                updates.append("scores = ?")
                params.append(json.dumps(scores))
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            if status in ("completed", "failed"):
                updates.append("completed_at = ?")
                params.append(datetime.now().isoformat())

            if not updates:
                return True

            params.append(generation_id)

            conn.execute(
                f"UPDATE generations SET {', '.join(updates)} WHERE id = ?", params
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update generation: {e}")
            conn.rollback()
            return False

    def get_generations_by_project(
        self, project_id: str, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        获取项目的生成历史

        Args:
            project_id: 项目ID
            limit: 最大返回数量
            offset: 偏移量

        Returns:
            生成记录列表
        """
        conn = self._pool.get_connection()
        cursor = conn.execute(
            """
            SELECT id, project_id, chapter_id, chapter_title, word_count,
                   iteration_count, scores, status, error_message, created_at, completed_at
            FROM generations 
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, limit, offset),
        )

        return [self._row_to_generation(row) for row in cursor.fetchall()]

    def get_generation(self, generation_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单个生成记录

        Args:
            generation_id: 生成ID

        Returns:
            生成记录
        """
        conn = self._pool.get_connection()
        cursor = conn.execute(
            "SELECT * FROM generations WHERE id = ?", (generation_id,)
        )
        row = cursor.fetchone()

        if row:
            return self._row_to_generation(row)
        return None

    def _row_to_generation(self, row: sqlite3.Row) -> Dict[str, Any]:
        """将数据库行转换为生成记录字典"""
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "chapter_id": row["chapter_id"],
            "chapter_title": row["chapter_title"],
            "word_count": row["word_count"],
            "iteration_count": row["iteration_count"],
            "scores": json.loads(row["scores"]) if row["scores"] else None,
            "status": row["status"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }


# =============================================================================
# 全局单例
# =============================================================================

_db_instance: Optional[ConnectionPool] = None
_db_lock = threading.Lock()

_agent_store_instance: Optional[AgentStateStore] = None
_generation_store_instance: Optional[GenerationHistoryStore] = None


def get_database(db_path: str = "data/agent_pro.db") -> ConnectionPool:
    """
    获取数据库连接池单例

    Args:
        db_path: 数据库文件路径

    Returns:
        连接池实例
    """
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = ConnectionPool(db_path)
    return _db_instance


def get_agent_state_store(db_path: str = "data/agent_pro.db") -> AgentStateStore:
    """获取Agent状态存储单例"""
    global _agent_store_instance
    if _agent_store_instance is None:
        with _db_lock:
            if _agent_store_instance is None:
                pool = get_database(db_path)
                _agent_store_instance = AgentStateStore(pool)
    return _agent_store_instance


def get_generation_history_store(
    db_path: str = "data/agent_pro.db",
) -> GenerationHistoryStore:
    """获取生成历史存储单例"""
    global _generation_store_instance
    if _generation_store_instance is None:
        with _db_lock:
            if _generation_store_instance is None:
                pool = get_database(db_path)
                _generation_store_instance = GenerationHistoryStore(pool)
    return _generation_store_instance


def close_database() -> None:
    """关闭数据库连接（用于应用退出时）"""
    global _db_instance, _agent_store_instance, _generation_store_instance

    if _db_instance:
        _db_instance.close_all()
        _db_instance = None
        _agent_store_instance = None
        _generation_store_instance = None
