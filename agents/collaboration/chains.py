"""
链式协作模式

V2.0版本
创建日期: 2026-03-21

特点:
- 线性串联，顺序执行
- 后任务依赖前任务
- 适用于标准生成流程
"""

from ..priority import AgentTask, TaskPriority
from typing import List, Dict, Any
import uuid


class ChainCollaboration:
    """
    链式协作模式

    任务按顺序执行，每个任务依赖前一个任务
    适用于: 标准生成流程(规划→思考→优化→验证)
    """

    @staticmethod
    def create_chain(
        tasks_data: List[Dict[str, Any]], dependencies_prefix: str = ""
    ) -> List[AgentTask]:
        """
        创建链式任务链

        Args:
            tasks_data: 任务数据列表
                [{"agent_type": "planner", "payload": {...}}, ...]
            dependencies_prefix: 依赖ID前缀

        Returns:
            AgentTask列表
        """
        tasks = []
        previous_task_id = None

        for i, task_data in enumerate(tasks_data):
            # 生成任务ID
            task_id = task_data.get("task_id") or f"{dependencies_prefix}chain_task_{i}"

            # 设置依赖（第一个任务无依赖）
            dependencies = [previous_task_id] if previous_task_id else []

            # 创建任务
            task = AgentTask(
                task_id=task_id,
                agent_type=task_data["agent_type"],
                priority=task_data.get("priority", TaskPriority.CRITICAL),
                payload=task_data["payload"],
                dependencies=dependencies,
            )

            tasks.append(task)
            previous_task_id = task_id

        return tasks

    @staticmethod
    def create_parallel_chains(
        chains_data: List[List[Dict[str, Any]]],
        merge_agent_type: str = None,
        merge_payload: Dict[str, Any] = None,
        prefix: str = "",
    ) -> List[AgentTask]:
        """
        创建并行链（多条链并行执行，最后合并）

        Args:
            chains_data: 多条链的任务数据
            merge_agent_type: 合并Agent类型
            merge_payload: 合并任务载荷
            prefix: 任务ID前缀

        Returns:
            AgentTask列表
        """
        all_tasks = []
        chain_end_ids = []

        # 创建各条链
        for chain_idx, chain_data in enumerate(chains_data):
            chain_prefix = f"{prefix}chain_{chain_idx}_"
            chain_tasks = ChainCollaboration.create_chain(
                chain_data, dependencies_prefix=chain_prefix
            )
            all_tasks.extend(chain_tasks)

            # 记录链尾任务ID
            if chain_tasks:
                chain_end_ids.append(chain_tasks[-1].task_id)

        # 创建合并任务（如果指定）
        if merge_agent_type and chain_end_ids:
            merge_task = AgentTask(
                task_id=f"{prefix}merge_task",
                agent_type=merge_agent_type,
                priority=TaskPriority.CRITICAL,
                payload=merge_payload or {},
                dependencies=chain_end_ids,
            )
            all_tasks.append(merge_task)

        return all_tasks


def create_generation_chain(generation_data: Dict) -> List[AgentTask]:
    """
    创建生成任务链

    标准流程: Planner → Thinker → Optimizer → Validator

    Args:
        generation_data: 生成请求数据

    Returns:
        任务链
    """
    return ChainCollaboration.create_chain(
        [
            {"agent_type": "planner", "payload": generation_data},
            {"agent_type": "thinker", "payload": generation_data},
            {"agent_type": "optimizer", "payload": generation_data},
            {"agent_type": "validator", "payload": generation_data},
        ],
        dependencies_prefix="generation_",
    )


def create_v5_generation_chain(generation_data: Dict) -> List[AgentTask]:
    """
    创建V5风格生成任务链

    V5流程: Outline → Context → Generator → Validator

    Args:
        generation_data: 生成请求数据

    Returns:
        任务链
    """
    return ChainCollaboration.create_chain(
        [
            {"agent_type": "outline_parser", "payload": generation_data},
            {"agent_type": "context_builder", "payload": generation_data},
            {"agent_type": "iterative_generator", "payload": generation_data},
            {"agent_type": "weighted_validator", "payload": generation_data},
        ],
        dependencies_prefix="v5_generation_",
    )
