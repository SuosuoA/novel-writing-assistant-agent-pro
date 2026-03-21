"""
Agent任务优先级队列

V2.0版本
创建日期: 2026-03-21

特性:
- 堆排序实现优先级队列
- 线程安全
- O(log n)插入/删除复杂度
"""

import heapq
import threading
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime, timezone

from .priority import AgentTask, TaskPriority


class AgentTaskQueue:
    """
    Agent任务优先级队列

    使用堆排序实现，支持多级优先级
    """

    def __init__(self):
        """初始化队列"""
        self._queues: Dict[TaskPriority, List[tuple]] = defaultdict(list)
        self._task_map: Dict[str, AgentTask] = {}  # task_id -> task
        self._lock = threading.RLock()

    def push(self, task: AgentTask) -> bool:
        """
        添加任务到队列

        Args:
            task: 任务对象

        Returns:
            是否添加成功（任务已存在返回False）
        """
        with self._lock:
            # 检查是否已存在
            if task.task_id in self._task_map:
                return False

            # 计算优先级分数: (priority, age_seconds)
            # 优先级越高(数值越小)优先，同优先级下任务越老越优先
            priority_score = (task.priority, task.age_seconds)
            heapq.heappush(self._queues[task.priority], (priority_score, task.task_id))
            self._task_map[task.task_id] = task
            return True

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

        Args:
            task_id: 任务ID

        Returns:
            是否移除成功
        """
        with self._lock:
            if task_id not in self._task_map:
                return False

            task = self._task_map[task_id]
            # 标记为已删除(惰性删除，避免O(n)移除)
            task.task_id = None
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
