"""
Agent系统模块

V2.0版本
创建日期: 2026-03-21

模块结构:
- priority: 任务优先级定义
- agent_state: Agent状态管理
- agent_constraints: Agent执行约束
- task_queue: 优先级任务队列
- dependency_resolver: 依赖解析器
- dependency_state: 依赖状态管理
- retry_manager: 重试管理器
- base_agent: Agent抽象基类
- agent_adapter: Agent适配器基类
- agent_pool: Agent池管理
- master_agent: MasterAgent总控调度器
- adapters: V5模块适配器
- collaboration: Agent协作模式
"""

from .priority import AgentTask, TaskPriority
from .agent_state import AgentState, AgentStatus
from .agent_constraints import (
    AgentConstraints,
    ThinkerConstraints,
    OptimizerConstraints,
    ValidatorConstraints,
    PlannerConstraints,
)
from .task_queue import AgentTaskQueue
from .dependency_resolver import DependencyResolver
from .dependency_state import DependencyState
from .retry_manager import RetryManager, RetryConfig, RetryPolicy
from .base_agent import BaseAgent
from .agent_adapter import AgentAdapter
from .agent_pool import AgentPool
from .master_agent import MasterAgent

__all__ = [
    # Priority
    "AgentTask",
    "TaskPriority",
    # Agent State
    "AgentState",
    "AgentStatus",
    # Agent Constraints
    "AgentConstraints",
    "ThinkerConstraints",
    "OptimizerConstraints",
    "ValidatorConstraints",
    "PlannerConstraints",
    # Task Queue
    "AgentTaskQueue",
    # Dependency
    "DependencyResolver",
    "DependencyState",
    # Retry
    "RetryManager",
    "RetryConfig",
    "RetryPolicy",
    # Agent Base
    "BaseAgent",
    "AgentAdapter",
    # Agent Pool
    "AgentPool",
    # Master Agent
    "MasterAgent",
]
