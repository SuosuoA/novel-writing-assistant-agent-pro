"""
任务依赖解析器

V2.0版本
创建日期: 2026-03-21

特性:
- DAG依赖图构建
- Kahn拓扑排序算法
- 循环依赖检测
"""

from typing import Dict, List, Set
from collections import defaultdict, deque

from .priority import AgentTask


class DependencyResolver:
    """
    任务依赖解析器

    使用DAG表示任务依赖关系，支持拓扑排序
    """

    def __init__(self):
        """初始化解析器"""
        self._dependency_graph: Dict[str, Set[str]] = defaultdict(
            set
        )  # task_id -> dependencies
        self._reverse_graph: Dict[str, Set[str]] = defaultdict(
            set
        )  # task_id -> dependents

    def build_graph(self, tasks: Dict[str, AgentTask]) -> List[str]:
        """
        构建依赖图并返回拓扑排序后的任务ID列表

        Args:
            tasks: 任务字典 {task_id: AgentTask}

        Returns:
            拓扑排序后的任务ID列表

        Raises:
            ValueError: 存在循环依赖
        """
        # 清空现有图
        self._dependency_graph.clear()
        self._reverse_graph.clear()

        # 构建图
        for task_id, task in tasks.items():
            self._dependency_graph[task_id] = set(task.dependencies)
            for dep_id in task.dependencies:
                self._reverse_graph[dep_id].add(task_id)

        # 拓扑排序(Kahn算法)
        return self._topological_sort(set(tasks.keys()))

    def _topological_sort(self, task_ids: Set[str]) -> List[str]:
        """
        Kahn算法拓扑排序

        Args:
            task_ids: 所有任务ID集合

        Returns:
            拓扑排序后的任务ID列表

        Raises:
            ValueError: 存在循环依赖
        """
        # 计算入度
        in_degree = {task_id: 0 for task_id in task_ids}
        for task_id in task_ids:
            for dep_id in self._dependency_graph[task_id]:
                in_degree[task_id] += 1

        # 找出入度为0的节点
        queue = deque([task_id for task_id in task_ids if in_degree[task_id] == 0])
        sorted_tasks = []

        while queue:
            task_id = queue.popleft()
            sorted_tasks.append(task_id)

            # 减少依赖此任务的节点的入度
            for dependent_id in self._reverse_graph[task_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        # 检查是否有循环依赖
        if len(sorted_tasks) != len(task_ids):
            remaining = set(task_ids) - set(sorted_tasks)
            raise ValueError(f"检测到循环依赖，涉及任务: {remaining}")

        return sorted_tasks

    def get_ready_tasks(self, completed_tasks: Set[str]) -> List[str]:
        """
        获取可执行的任务(所有依赖已完成)

        Args:
            completed_tasks: 已完成的任务ID集合

        Returns:
            可执行的任务ID列表
        """
        ready_tasks = []
        for task_id, dependencies in self._dependency_graph.items():
            if dependencies.issubset(completed_tasks):
                ready_tasks.append(task_id)
        return ready_tasks
