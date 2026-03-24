"""
Agent核心模块

V1.0版本
创建日期: 2026-03-23

模块结构:
- base_agent: Agent基类和数据类型定义
- master_agent: MasterAgent调度器
"""

from .base_agent import (
    # 枚举
    AgentCapability,
    AgentState,
    # 数据类
    AgentMetadata,
    AgentContext,
    AgentResult,
    AgentStatus,
    # 基类
    BaseAgent,
)

from .master_agent import (
    # 枚举
    TaskPriority,
    # 数据类
    TaskDefinition,
    PipelineStage,
    PipelineDefinition,
    # 组件
    AgentRegistry,
    TaskQueue,
    DependencyResolver,
    # 主调度器
    MasterAgent,
)

__all__ = [
    # 枚举
    "AgentCapability",
    "AgentState",
    "TaskPriority",
    # 数据类
    "AgentMetadata",
    "AgentContext",
    "AgentResult",
    "AgentStatus",
    "TaskDefinition",
    "PipelineStage",
    "PipelineDefinition",
    # 组件
    "AgentRegistry",
    "TaskQueue",
    "DependencyResolver",
    # 基类
    "BaseAgent",
    # 主调度器
    "MasterAgent",
]
