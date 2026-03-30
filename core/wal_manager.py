"""
WAL协议管理器 - OpenClaw核心机制

V1.0版本
创建日期：2026-03-25

特性：
- WAL协议（Write-Ahead Log）：AI调用前先持久化状态
- 同步写入（阻塞式）确保落盘，防止数据丢失
- 线程安全（RLock保护）
- EventBus集成（发布WAL事件）
- 单例工厂模式

设计参考：
- OpenClaw mem9 WAL协议
- 升级方案10.1

核心原则：
在每次AI响应前，先将状态写入SESSION-STATE.md，确保：
1. 中断可恢复：如果AI调用过程中程序崩溃，可以从SESSION-STATE恢复
2. 数据不丢失：同步写入（fsync）确保数据落盘
3. 状态可追溯：完整记录AI调用前的上下文

使用示例：
    # 获取单例实例
    wal_manager = get_wal_manager()

    # AI调用前写入状态（阻塞式）
    wal_manager.write_before_ai_call({
        "operation": "生成第3章",
        "task_id": "task-001",
        "context": {
            "chapter_number": 3,
            "outline": "...",
            "characters": ["张三", "李四"]
        }
    })

    # 启动时恢复
    recovered = wal_manager.recover_on_startup()
    if recovered:
        print(f"恢复上次会话: {recovered['operation']}")
"""

import json
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, Field, ConfigDict

from .models import Event


# ============================================================================
# Pydantic数据模型
# ============================================================================


class WALRecord(BaseModel):
    """WAL记录"""

    model_config = ConfigDict(frozen=False)

    record_id: str = Field("", description="记录ID（时间戳）")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="记录时间"
    )
    operation: str = Field("", description="操作描述")
    task_id: Optional[str] = Field(None, description="任务ID")
    context: Dict[str, Any] = Field(default_factory=dict, description="上下文数据")
    status: str = Field("pending", description="状态：pending/completed/failed")
    error: Optional[str] = Field(None, description="错误信息")


class WALState(BaseModel):
    """WAL状态"""

    model_config = ConfigDict(frozen=False)

    current_record: Optional[WALRecord] = Field(None, description="当前WAL记录")
    last_write_time: Optional[str] = Field(None, description="上次写入时间")
    total_writes: int = Field(0, ge=0, description="总写入次数")
    failed_writes: int = Field(0, ge=0, description="失败写入次数")


# ============================================================================
# WAL管理器
# ============================================================================


class WALManager:
    """
    WAL协议管理器 - 在AI响应前先写入状态

    核心机制：
    1. 同步写入：使用fsync确保数据落盘
    2. 阻塞式写入：AI调用前必须完成写入
    3. 状态追踪：记录每次AI调用的上下文
    4. 中断恢复：启动时检查未完成的WAL记录

    线程安全：
    - 使用RLock保护状态更新
    - 写入操作原子化
    """

    def __init__(self, workspace: Path):
        """
        初始化WAL管理器

        Args:
            workspace: 工作区根目录
        """
        self.workspace = workspace
        self.wal_file = workspace / ".workbuddy" / "wal.json"
        self.wal_file.parent.mkdir(parents=True, exist_ok=True)

        # 线程锁
        self._write_lock = threading.RLock()
        self._state_lock = threading.RLock()

        # WAL状态
        self._state = WALState()

        # EventBus延迟导入（避免循环依赖）
        self._event_bus = None

        # 启动时恢复
        self._recover_state()

    def _get_event_bus(self):
        """延迟获取EventBus实例"""
        if self._event_bus is None:
            try:
                from .event_bus import get_event_bus
                self._event_bus = get_event_bus()
            except ImportError:
                self._event_bus = None
        return self._event_bus

    def _publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """发布事件"""
        event_bus = self._get_event_bus()
        if event_bus:
            try:
                # EventBus.publish签名: publish(event_type, data, source)
                event_bus.publish(
                    event_type=event_type,
                    data=data,
                    source="WALManager"
                )
            except Exception as e:
                # 事件发布失败不应影响主流程
                print(f"[WALManager] 事件发布失败: {e}")

    def _recover_state(self) -> None:
        """启动时恢复WAL状态"""
        if not self.wal_file.exists():
            return

        try:
            with open(self.wal_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._state = WALState(**data)

            # 检查是否有未完成的WAL记录
            if (self._state.current_record and 
                self._state.current_record.status == "pending"):
                print(f"[WALManager] 发现未完成的WAL记录: {self._state.current_record.operation}")
                # 发布恢复事件
                self._publish_event("wal.recovery.needed", {
                    "record": self._state.current_record.model_dump()
                })

        except Exception as e:
            print(f"[WALManager] 状态恢复失败: {e}")
            # 恢复失败时重置状态
            self._state = WALState()

    def write_before_ai_call(
        self,
        context: Dict[str, Any],
        operation: str = "",
        task_id: Optional[str] = None
    ) -> bool:
        """
        WAL协议：在AI调用前写入状态（同步阻塞式）

        这是WAL协议的核心方法，必须在调用LLM API之前调用。
        使用同步写入（fsync）确保数据落盘，防止崩溃丢失。

        Args:
            context: AI调用的上下文数据
            operation: 操作描述（如："生成第3章"）
            task_id: 任务ID（可选）

        Returns:
            bool: 写入是否成功

        Example:
            # AI调用前
            success = wal_manager.write_before_ai_call(
                context={
                    "chapter_number": 3,
                    "outline": "...",
                    "characters": ["张三"]
                },
                operation="生成第3章",
                task_id="task-001"
            )

            if not success:
                raise RuntimeError("WAL写入失败，无法继续")

            # 调用AI
            result = llm_api.generate(...)
        """
        with self._write_lock:
            try:
                # 创建WAL记录
                record = WALRecord(
                    record_id=datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
                    timestamp=datetime.now().isoformat(),
                    operation=operation or context.get("operation", ""),
                    task_id=task_id or context.get("task_id"),
                    context=context,
                    status="pending"
                )

                # 更新状态
                with self._state_lock:
                    self._state.current_record = record
                    self._state.last_write_time = record.timestamp
                    self._state.total_writes += 1

                # 同步写入文件（阻塞式）
                self._write_state_to_disk()

                # 发布WAL写入事件
                self._publish_event("wal.write.success", {
                    "record_id": record.record_id,
                    "operation": record.operation,
                    "timestamp": record.timestamp
                })

                return True

            except Exception as e:
                # 写入失败
                with self._state_lock:
                    self._state.failed_writes += 1

                error_msg = f"{type(e).__name__}: {str(e)}"
                print(f"[WALManager] WAL写入失败: {error_msg}")

                # 发布失败事件
                self._publish_event("wal.write.failed", {
                    "error": error_msg,
                    "operation": operation
                })

                return False

    def mark_completed(self, result: Optional[Dict[str, Any]] = None) -> None:
        """
        标记当前WAL记录为已完成

        在AI调用成功完成后调用，标记WAL记录状态为completed。

        Args:
            result: AI调用的结果（可选）
        """
        with self._state_lock:
            if self._state.current_record:
                self._state.current_record.status = "completed"
                if result:
                    self._state.current_record.context["result"] = result

                # 写入状态
                self._write_state_to_disk()

                # 发布完成事件
                self._publish_event("wal.completed", {
                    "record_id": self._state.current_record.record_id,
                    "operation": self._state.current_record.operation
                })

    def mark_failed(self, error: str) -> None:
        """
        标记当前WAL记录为失败

        在AI调用失败后调用，标记WAL记录状态为failed。

        Args:
            error: 错误信息
        """
        with self._state_lock:
            if self._state.current_record:
                self._state.current_record.status = "failed"
                self._state.current_record.error = error

                # 写入状态
                self._write_state_to_disk()

                # 发布失败事件
                self._publish_event("wal.failed", {
                    "record_id": self._state.current_record.record_id,
                    "operation": self._state.current_record.operation,
                    "error": error
                })

    def _write_state_to_disk(self) -> None:
        """
        同步写入状态到磁盘（阻塞式）

        使用fsync确保数据真正落盘，这是WAL协议的核心。
        """
        # 序列化状态
        state_data = self._state.model_dump()

        # 写入临时文件（原子化写入）
        temp_file = self.wal_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
                f.flush()  # 刷新缓冲区
                # fsync确保落盘（关键！）
                import os
                os.fsync(f.fileno())

            # 原子化重命名
            temp_file.replace(self.wal_file)

        except Exception as e:
            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()
            raise e

    def recover_on_startup(self) -> Optional[Dict[str, Any]]:
        """
        启动时恢复上次会话状态

        Returns:
            Optional[Dict]: 恢复的状态数据，如果没有则返回None

        Example:
            recovered = wal_manager.recover_on_startup()
            if recovered:
                print(f"恢复上次未完成的操作: {recovered['operation']}")
                # 继续执行或提示用户
        """
        if not self._state.current_record:
            return None

        record = self._state.current_record

        # 只返回pending状态的记录（未完成的AI调用）
        if record.status == "pending":
            return {
                "record_id": record.record_id,
                "timestamp": record.timestamp,
                "operation": record.operation,
                "task_id": record.task_id,
                "context": record.context
            }

        return None

    def get_wal_stats(self) -> Dict[str, Any]:
        """
        获取WAL统计信息

        Returns:
            Dict: 统计信息
        """
        with self._state_lock:
            return {
                "total_writes": self._state.total_writes,
                "failed_writes": self._state.failed_writes,
                "success_rate": (
                    (self._state.total_writes - self._state.failed_writes) / 
                    self._state.total_writes * 100
                ) if self._state.total_writes > 0 else 0,
                "last_write_time": self._state.last_write_time,
                "has_pending_record": (
                    self._state.current_record is not None and
                    self._state.current_record.status == "pending"
                )
            }

    def clear_wal(self) -> None:
        """
        清空WAL状态

        用于测试或手动清理。
        """
        with self._state_lock:
            self._state = WALState()

        # 删除WAL文件
        if self.wal_file.exists():
            self.wal_file.unlink()

        # 发布清空事件
        self._publish_event("wal.cleared", {})


# ============================================================================
# 单例工厂
# ============================================================================

_wal_manager_instance: Optional[WALManager] = None
_wal_manager_lock = threading.Lock()


def get_wal_manager(workspace: Optional[Path] = None) -> WALManager:
    """
    获取WAL管理器单例实例

    Args:
        workspace: 工作区路径（可选，默认为当前工作目录）

    Returns:
        WALManager: WAL管理器实例
    """
    global _wal_manager_instance

    if _wal_manager_instance is None:
        with _wal_manager_lock:
            if _wal_manager_instance is None:
                if workspace is None:
                    # 默认使用项目根目录
                    workspace = Path.cwd()
                _wal_manager_instance = WALManager(workspace)

    return _wal_manager_instance


def reset_wal_manager() -> None:
    """
    重置WAL管理器单例（仅用于测试）
    """
    global _wal_manager_instance

    with _wal_manager_lock:
        if _wal_manager_instance is not None:
            _wal_manager_instance = None
