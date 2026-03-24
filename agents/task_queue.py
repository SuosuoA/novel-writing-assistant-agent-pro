"""
Agent任务优先级队列

V2.1版本 - 安全加固
创建日期: 2026-03-21
更新日期: 2026-03-24

安全修复:
- P1-3: 添加队列容量限制，防止内存耗尽

特性:
- 堆排序实现优先级队列
- 线程安全
- O(log n)插入/删除复杂度
"""

import heapq
import threading
import logging
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime, timezone

from .priority import AgentTask, TaskPriority, MAX_TASK_QUEUE_SIZE

logger = logging.getLogger(__name__)


class AgentTaskQueue:
    """
    Agent任务优先级队列（V2.1安全加固版）

    使用堆排序实现，支持多级优先级
    
    P1-3修复: 添加容量限制，防止内存耗尽
    """

    def __init__(self, max_size: int = MAX_TASK_QUEUE_SIZE):
        """
        初始化队列

        Args:
            max_size: 队列最大容量（默认1000）
        """
        self._queues: Dict[TaskPriority, List[tuple]] = defaultdict(list)
        self._task_map: Dict[str, AgentTask] = {}  # task_id -> task
        self._lock = threading.RLock()
        self._max_size = max_size
        self._rejected_count = 0  # 拒绝任务计数（用于监控）

    def push(self, task: AgentTask) -> bool:
        """
        添加任务到队列

        P1-3修复: 添加容量检查，队列满时拒绝新任务

        Args:
            task: 任务对象

        Returns:
            是否添加成功（任务已存在或队列已满返回False）
        """
        with self._lock:
            # 检查是否已存在
            if task.task_id in self._task_map:
                return False

            # P1-3: 检查队列容量
            if len(self._task_map) >= self._max_size:
                self._rejected_count += 1
                logger.warning(
                    f"任务队列已满 ({self._max_size})，拒绝任务: {task.task_id} "
                    f"(累计拒绝: {self._rejected_count})"
                )
                return False

            # 计算优先级分数: (priority, age_seconds)
            # 优先级越高(数值越小)优先，同优先级下任务越老越优先
            priority_score = (task.priority, task.age_seconds)
            heapq.heappush(self._queues[task.priority], (priority_score, task.task_id))
            self._task_map[task.task_id] = task
            return True
    
    @property
    def max_size(self) -> int:
        """获取队列最大容量"""
        return self._max_size
    
    @property
    def rejected_count(self) -> int:
        """获取拒绝任务计数"""
        return self._rejected_count
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取队列统计信息

        Returns:
            包含队列大小、容量、拒绝计数的字典
        """
        with self._lock:
            return {
                "size": len(self._task_map),
                "max_size": self._max_size,
                "rejected_count": self._rejected_count,
                "utilization": len(self._task_map) / self._max_size if self._max_size > 0 else 0,
            }

    def pop(self) -> Optional[AgentTask]:
        """
        弹出最高优先级任务

        Returns:
            任务对象，队列为空返回None
        """
        with self._lock:
            # 按优先级顺序检查队列
            for priority in sorted(TaskPriority):
                if self._queues[priority]:
                    priority_score, task_id = heapq.heappop(self._queues[priority])
                    task = self._task_map.pop(task_id, None)
                    if task:
                        task.started_at = datetime.now(timezone.utc)
                        return task
            return None

    def peek(self) -> Optional[AgentTask]:
        """
        查看最高优先级任务(不移除)

        Returns:
            任务对象，队列为空返回None
        """
        with self._lock:
            for priority in sorted(TaskPriority):
                if self._queues[priority]:
                    _, task_id = self._queues[priority][0]
                    return self._task_map.get(task_id)
            return None

    def remove(self, task_id: str) -> bool:
        """
        移除任务(取消任务)

        修复：从堆中也移除任务，避免内存泄漏

        Args:
            task_id: 任务ID

        Returns:
            是否移除成功
        """
        with self._lock:
            if task_id not in self._task_map:
                return False

            task = self._task_map[task_id]
            priority = task.priority

            # 从堆中移除（需要重建堆）
            self._queues[priority] = [
                item for item in self._queues[priority]
                if item[1] != task_id
            ]
            heapq.heapify(self._queues[priority])

            del self._task_map[task_id]
            return True

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        """
        获取任务(不移除)

        Args:
            task_id: 任务ID

        Returns:
            任务对象，不存在返回None
        """
        with self._lock:
            return self._task_map.get(task_id)

    def size(self) -> int:
        """
        队列大小

        Returns:
            任务数量
        """
        with self._lock:
            return len(self._task_map)

    def empty(self) -> bool:
        """
        队列是否为空

        Returns:
            是否为空
        """
        return self.size() == 0

    def clear(self) -> None:
        """清空队列"""
        with self._lock:
            self._queues.clear()
            self._task_map.clear()
