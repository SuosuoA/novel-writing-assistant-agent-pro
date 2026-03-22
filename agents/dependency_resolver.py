"""
任务依赖解析器

V2.1版本
创建日期: 2026-03-21
修订日期: 2026-03-23

特性:
- DAG依赖图构建
- Kahn拓扑排序算法
- 循环依赖检测
- 版本冲突检查（V2.1新增）
"""

import re
from typing import Dict, List, Set, Optional
from collections import defaultdict, deque

from .priority import AgentTask


class VersionConflictError(Exception):
    """版本冲突异常"""
    pass


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
            VersionConflictError: 存在版本冲突
        """
        # 清空现有图
        self._dependency_graph.clear()
        self._reverse_graph.clear()

        # 构建图
        for task_id, task in tasks.items():
            self._dependency_graph[task_id] = set(task.dependencies)
            for dep_id in task.dependencies:
                self._reverse_graph[dep_id].add(task_id)

        # 版本冲突检查
        self._check_version_conflicts(tasks)

        # 拓扑排序(Kahn算法)
        return self._topological_sort(set(tasks.keys()))

    def _check_version_conflicts(self, tasks: Dict[str, AgentTask]) -> None:
        """
        检查依赖版本冲突

        Args:
            tasks: 任务字典

        Raises:
            VersionConflictError: 存在版本冲突
        """
        for task_id, task in tasks.items():
            if not task.dependency_versions:
                continue

            for dep_id, required_version in task.dependency_versions.items():
                if dep_id not in tasks:
                    continue  # 依赖不存在会在后续检查中报告

                dep_task = tasks[dep_id]
                actual_version = dep_task.version

                if not self._check_version_compatible(required_version, actual_version):
                    raise VersionConflictError(
                        f"版本冲突: {task_id} 需要 {dep_id}@{required_version}, "
                        f"实际版本 {actual_version}"
                    )

    def _check_version_compatible(self, required: str, actual: str) -> bool:
        """
        检查版本兼容性

        支持语义化版本比较:
        - "1.0.0": 精确匹配
        - ">=1.0.0": 大于等于
        - ">=1.0.0,<2.0.0": 范围
        - "^1.0.0": 兼容版本（主版本相同）

        Args:
            required: 要求的版本
            actual: 实际版本

        Returns:
            是否兼容
        """
        # 简单实现：精确匹配
        if required == actual:
            return True

        # 处理 ^ 前缀（兼容版本）
        if required.startswith("^"):
            req_parts = required[1:].split(".")
            act_parts = actual.split(".")
            # 主版本号必须相同
            if len(req_parts) >= 1 and len(act_parts) >= 1:
                return req_parts[0] == act_parts[0]
            return False

        # 处理 >= 前缀
        if required.startswith(">="):
            req_version = required[2:]
            return self._compare_versions(actual, req_version) >= 0

        # 处理 > 前缀
        if required.startswith(">"):
            req_version = required[1:]
            return self._compare_versions(actual, req_version) > 0

        # 处理 <= 前缀
        if required.startswith("<="):
            req_version = required[2:]
            return self._compare_versions(actual, req_version) <= 0

        # 处理 < 前缀
        if required.startswith("<"):
            req_version = required[1:]
            return self._compare_versions(actual, req_version) < 0

        # 处理范围（用逗号分隔）
        if "," in required:
            conditions = required.split(",")
            for cond in conditions:
                cond = cond.strip()
                if cond.startswith(">="):
                    if self._compare_versions(actual, cond[2:]) < 0:
                        return False
                elif cond.startswith(">"):
                    if self._compare_versions(actual, cond[1:]) <= 0:
                        return False
                elif cond.startswith("<="):
                    if self._compare_versions(actual, cond[2:]) > 0:
                        return False
                elif cond.startswith("<"):
                    if self._compare_versions(actual, cond[1:]) >= 0:
                        return False
            return True

        # 默认：不兼容
        return False

    def _compare_versions(self, v1: str, v2: str) -> int:
        """
        比较两个版本号

        Args:
            v1: 版本1
            v2: 版本2

        Returns:
            v1 > v2 返回正数，v1 < v2 返回负数，相等返回0
        """
        parts1 = [int(p) for p in v1.split(".")]
        parts2 = [int(p) for p in v2.split(".")]

        # 补齐长度
        max_len = max(len(parts1), len(parts2))
        parts1.extend([0] * (max_len - len(parts1)))
        parts2.extend([0] * (max_len - len(parts2)))

        for p1, p2 in zip(parts1, parts2):
            if p1 != p2:
                return p1 - p2
        return 0

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
