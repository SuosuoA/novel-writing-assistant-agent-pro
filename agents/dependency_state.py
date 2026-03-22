"""
依赖状态管理器

V2.0版本
创建日期: 2026-03-21

特性:
- 任务状态跟踪
- 线程安全
"""

from typing import Dict, Set, List
from datetime import datetime, timezone
import threading


class DependencyState:
    """
    依赖状态管理器

    管理任务的执行状态（pending/in_progress/completed/failed）
    """

    def __init__(self):
        """初始化状态管理器"""
        self._completed: Set[str] = set()
        self._failed: Set[str] = set()
        self._in_progress: Set[str] = set()
        self._lock = threading.RLock()

    def mark_in_progress(self, task_id: str) -> bool:
        """
        标记任务为进行中

        Args:
            task_id: 任务ID

        Returns:
            是否标记成功
        """
        with self._lock:
            if task_id in self._completed or task_id in self._failed:
                return False
            self._in_progress.add(task_id)
            return True

    def mark_completed(self, task_id: str) -> bool:
        """
        标记任务为已完成

        Args:
            task_id: 任务ID

        Returns:
            是否标记成功
        """
        with self._lock:
            if task_id not in self._in_progress:
                return False
            self._in_progress.discard(task_id)
            self._completed.add(task_id)
            return True

    def mark_failed(self, task_id: str) -> bool:
        """
        标记任务为失败

        Args:
            task_id: 任务ID

        Returns:
            是否标记成功
        """
        with self._lock:
            self._in_progress.discard(task_id)
            self._failed.add(task_id)
            return True

    def mark_pending(self, task_id: str) -> bool:
        """
        标记任务为待执行（用于重试任务重新入队）

        Args:
            task_id: 任务ID

        Returns:
            是否标记成功
        """
        with self._lock:
            # 从in_progress移除，改为pending状态
            self._in_progress.discard(task_id)
            # 不加入任何集合，pending是默认状态
            return True

    def is_ready(self, task_id: str, dependencies: List[str]) -> bool:
        """
        检查任务是否可执行(所有依赖已完成)

        Args:
            task_id: 任务ID
            dependencies: 依赖任务ID列表

        Returns:
            是否可执行
        """
        with self._lock:
            # 依赖不能有失败的
            if any(dep in self._failed for dep in dependencies):
                return False
            # 所有依赖必须已完成
            return all(dep in self._completed for dep in dependencies)

    def get_status(self, task_id: str) -> str:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            状态字符串: pending/in_progress/completed/failed
        """
        with self._lock:
            if task_id in self._completed:
                return "completed"
            elif task_id in self._failed:
                return "failed"
            elif task_id in self._in_progress:
                return "in_progress"
            else:
                return "pending"

    def reset(self) -> None:
        """重置所有状态"""
        with self._lock:
            self._completed.clear()
            self._failed.clear()
            self._in_progress.clear()

    @property
    def completed(self) -> Set[str]:
        """获取已完成的任务ID集合"""
        with self._lock:
            return self._completed.copy()

    @property
    def failed(self) -> Set[str]:
        """获取失败的任务ID集合"""
        with self._lock:
            return self._failed.copy()

    @property
    def in_progress(self) -> Set[str]:
        """获取进行中的任务ID集合"""
        with self._lock:
            return self._in_progress.copy()
