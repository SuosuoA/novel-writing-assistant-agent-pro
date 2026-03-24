"""
Agent系统模块

V2.1版本
更新日期: 2026-03-24

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
- plugins: 插件Agent（调用实际插件）
- collaboration: Agent协作模式
- pipeline_orchestrator: 流水线编排器（V2.1新增）
- novel_generation_service: 小说生成服务（V2.1新增）
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

# P0修复：导出plugins模块，支持 from agents.plugins import ... 导入
from . import plugins

# P0修复：从plugins模块导出4个Agent适配器，支持 from agents import OutlineAnalysisAgent 导入
from .plugins import (
    OutlineAnalysisAgent,
    StyleLearningAgent,
    NovelGenerationAgent,
    QualityValidationAgent,
)

# P1修复：导出流水线相关类
from .pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineState,
    PipelineExecutionResult,
    PipelineStageResult,
    NovelGenerationConfig,
    create_novel_generation_pipeline,
)
from .novel_generation_service import (
    NovelGenerationService,
    GenerationProgress,
    get_generation_service,
)

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
    # P0修复：添加plugins模块导出
    "plugins",
    # P0修复：添加4个Agent适配器导出
    "OutlineAnalysisAgent",
    "StyleLearningAgent",
    "NovelGenerationAgent",
    "QualityValidationAgent",
    # P1修复：添加流水线相关类导出
    "PipelineOrchestrator",
    "PipelineState",
    "PipelineExecutionResult",
    "PipelineStageResult",
    "NovelGenerationConfig",
    "create_novel_generation_pipeline",
    "NovelGenerationService",
    "GenerationProgress",
    "get_generation_service",
]
