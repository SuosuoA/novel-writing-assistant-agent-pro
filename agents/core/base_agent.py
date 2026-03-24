"""
Agent核心基类定义

V1.0版本
创建日期: 2026-03-23

特性:
- AgentMetadata: Agent元数据定义
- AgentContext: Agent执行上下文
- AgentResult: Agent执行结果
- BaseAgent: 抽象基类接口
- ServiceLocator集成支持
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Type
import logging

# 延迟导入，避免循环依赖
# from core.service_locator import ServiceLocator


class AgentCapability(str, Enum):
    """Agent能力枚举"""
    GENERATION = "generation"       # 内容生成
    ANALYSIS = "analysis"           # 内容分析
    VALIDATION = "validation"       # 质量验证
    OPTIMIZATION = "optimization"   # 内容优化
    PLANNING = "planning"           # 任务规划
    REASONING = "reasoning"         # 逻辑推理


class AgentState(Enum):
    """Agent状态枚举"""
    UNLOADED = "unloaded"           # 未加载
    LOADED = "loaded"               # 已加载(初始化中)
    ACTIVE = "active"               # 活跃(可接受任务)
    BUSY = "busy"                   # 忙碌(正在执行任务)
    ERROR = "error"                 # 错误(无法使用)
    SHUTTING_DOWN = "shutting_down" # 正在关闭


@dataclass
class AgentMetadata:
    """
    Agent元数据
    
    定义Agent的基本信息和能力描述
    """
    agent_type: str                          # Agent类型标识
    name: str                                # Agent名称
    description: str = ""                    # Agent描述
    version: str = "1.0.0"                   # 版本号
    capabilities: List[AgentCapability] = field(default_factory=list)  # 能力列表
    dependencies: List[str] = field(default_factory=list)              # 依赖的其他Agent
    tags: List[str] = field(default_factory=list)                      # 标签
    author: str = ""                         # 作者
    priority: int = 0                        # 默认优先级
    
    # 执行约束
    timeout_seconds: int = 30                # 超时时间
    max_retries: int = 1                     # 最大重试次数
    max_concurrent_tasks: int = 1            # 最大并发任务数
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_type": self.agent_type,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "dependencies": self.dependencies,
            "tags": self.tags,
            "author": self.author,
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_concurrent_tasks": self.max_concurrent_tasks,
        }


@dataclass
class AgentContext:
    """
    Agent执行上下文
    
    包含任务执行所需的所有上下文信息
    """
    task_id: str                             # 任务ID
    session_id: str = ""                     # 会话ID
    conversation_history: List[Dict] = field(default_factory=list)  # 对话历史
    shared_memory: Dict[str, Any] = field(default_factory=dict)     # 共享记忆
    metadata: Dict[str, Any] = field(default_factory=dict)          # 元数据
    config: Dict[str, Any] = field(default_factory=dict)            # 配置
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
    
    def add_message(self, role: str, content: str, **metadata) -> None:
        """添加消息到对话历史"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **metadata
        })
        self.updated_at = datetime.now(timezone.utc)
    
    def get_recent_messages(self, n: int = 5) -> List[Dict]:
        """获取最近n条消息"""
        return self.conversation_history[-n:]
    
    def set_shared(self, key: str, value: Any) -> None:
        """设置共享记忆"""
        self.shared_memory[key] = value
        self.updated_at = datetime.now(timezone.utc)
    
    def get_shared(self, key: str, default: Any = None) -> Any:
        """获取共享记忆"""
        return self.shared_memory.get(key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "conversation_history": self.conversation_history,
            "shared_memory": self.shared_memory,
            "metadata": self.metadata,
            "config": self.config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class AgentResult:
    """
    Agent执行结果
    
    标准化的任务执行结果结构
    """
    success: bool                            # 是否成功
    task_id: str                             # 任务ID
    agent_type: str                          # Agent类型
    data: Any = None                         # 结果数据
    error: Optional[str] = None              # 错误信息
    error_type: Optional[str] = None         # 错误类型
    metrics: Dict[str, Any] = field(default_factory=dict)   # 执行指标
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """执行耗时(秒)"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "data": self.data,
            "error": self.error,
            "error_type": self.error_type,
            "metrics": self.metrics,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
        }
    
    @classmethod
    def success_result(cls, task_id: str, agent_type: str, data: Any = None, **kwargs) -> "AgentResult":
        """创建成功结果"""
        return cls(
            success=True,
            task_id=task_id,
            agent_type=agent_type,
            data=data,
            completed_at=datetime.now(timezone.utc),
            **kwargs
        )
    
    @classmethod
    def failure_result(cls, task_id: str, agent_type: str, error: str, error_type: str = None, **kwargs) -> "AgentResult":
        """创建失败结果"""
        return cls(
            success=False,
            task_id=task_id,
            agent_type=agent_type,
            error=error,
            error_type=error_type or "AgentError",
            completed_at=datetime.now(timezone.utc),
            **kwargs
        )


@dataclass
class AgentStatus:
    """Agent运行状态"""
    agent_type: str
    state: AgentState
    current_task_id: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_active: Optional[datetime] = None
    error_message: Optional[str] = None
    initialized_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.initialized_at is None:
            self.initialized_at = datetime.now(timezone.utc)
    
    def update_last_active(self) -> None:
        """更新最后活跃时间"""
        self.last_active = datetime.now(timezone.utc)
    
    def increment_completed(self) -> None:
        """任务完成计数+1"""
        self.tasks_completed += 1
        self.update_last_active()
    
    def increment_failed(self) -> None:
        """任务失败计数+1"""
        self.tasks_failed += 1
        self.update_last_active()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_type": self.agent_type,
            "state": self.state.value,
            "current_task_id": self.current_task_id,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "error_message": self.error_message,
            "initialized_at": self.initialized_at.isoformat() if self.initialized_at else None,
        }


class BaseAgent(ABC):
    """
    Agent抽象基类
    
    所有Agent必须实现以下方法:
    - initialize(): 初始化Agent
    - execute(task): 执行任务
    - can_handle(task): 判断是否能处理任务
    - cleanup(): 清理资源
    
    通过ServiceLocator可访问核心服务:
    - self.get_service(service_type): 获取服务实例
    - self.get_config(): 获取配置
    - self.get_logger(): 获取日志器
    - self.get_event_bus(): 获取事件总线
    """
    
    def __init__(self, agent_type: str, metadata: AgentMetadata = None):
        """
        初始化Agent
        
        Args:
            agent_type: Agent类型标识
            metadata: Agent元数据（可选，不提供则使用默认值）
        """
        self.agent_type = agent_type
        self._metadata = metadata or self._create_default_metadata()
        self._status = AgentStatus(agent_type=agent_type, state=AgentState.UNLOADED)
        self._initialized = False
        self._service_locator = None  # 延迟注入
        self._logger: Optional[logging.Logger] = None
    
    def _create_default_metadata(self) -> AgentMetadata:
        """创建默认元数据"""
        return AgentMetadata(
            agent_type=self.agent_type,
            name=self.agent_type.replace("_", " ").title(),
            description=f"{self.agent_type} agent",
        )
    
    # === 抽象方法 ===
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        初始化Agent
        
        Returns:
            是否初始化成功
        """
        pass
    
    @abstractmethod
    def execute(self, task_id: str, payload: Dict[str, Any], context: AgentContext = None) -> AgentResult:
        """
        执行任务
        
        Args:
            task_id: 任务ID
            payload: 任务载荷
            context: 执行上下文
            
        Returns:
            AgentResult执行结果
        """
        pass
    
    @abstractmethod
    def can_handle(self, task_type: str, payload: Dict[str, Any]) -> bool:
        """
        判断是否能处理该任务
        
        Args:
            task_type: 任务类型
            payload: 任务载荷
            
        Returns:
            是否能处理
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> bool:
        """
        清理资源
        
        Returns:
            是否清理成功
        """
        pass
    
    # === 属性 ===
    
    @property
    def metadata(self) -> AgentMetadata:
        """获取Agent元数据"""
        return self._metadata
    
    @property
    def status(self) -> AgentStatus:
        """获取Agent状态"""
        return self._status
    
    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized
    
    # === ServiceLocator集成 ===
    
    def set_service_locator(self, service_locator) -> None:
        """
        设置服务定位器
        
        Args:
            service_locator: ServiceLocator实例
        """
        self._service_locator = service_locator
        self._logger = None  # 重置日志器，下次获取时从ServiceLocator获取
    
    def get_service(self, service_type: Type) -> Any:
        """
        获取服务实例
        
        Args:
            service_type: 服务类型
            
        Returns:
            服务实例，不存在返回None
        """
        if self._service_locator is None:
            return None
        return self._service_locator.try_get(service_type)
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        try:
            from core.config_service import ConfigService
            config_service = self.get_service(ConfigService)
            if config_service:
                return config_service.get_all()
        except ImportError:
            pass
        return {}
    
    def get_logger(self) -> logging.Logger:
        """获取日志器"""
        if self._logger is None:
            if self._service_locator:
                try:
                    from core.logging_service import LoggingService
                    logging_service = self.get_service(LoggingService)
                    if logging_service:
                        self._logger = logging_service.get_logger(f"agent.{self.agent_type}")
                except ImportError:
                    pass
            
            if self._logger is None:
                self._logger = logging.getLogger(f"agent.{self.agent_type}")
        
        return self._logger
    
    def get_event_bus(self):
        """获取事件总线"""
        try:
            from core.event_bus import EventBus
            return self.get_service(EventBus)
        except ImportError:
            return None
    
    # === 状态管理 ===
    
    def _set_state(self, state: AgentState) -> None:
        """设置状态"""
        self._status.state = state
    
    def _set_error(self, error: str) -> None:
        """设置错误信息"""
        self._status.error_message = error
    
    def _increment_completed(self) -> None:
        """完成任务计数+1"""
        self._status.increment_completed()
    
    def _increment_failed(self) -> None:
        """失败任务计数+1"""
        self._status.increment_failed()
    
    # === 健康检查 ===
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态信息
        """
        return {
            "agent_type": self.agent_type,
            "state": self._status.state.value,
            "initialized": self._initialized,
            "tasks_completed": self._status.tasks_completed,
            "tasks_failed": self._status.tasks_failed,
            "last_active": self._status.last_active.isoformat() if self._status.last_active else None,
            "error_message": self._status.error_message,
            "metadata": self._metadata.to_dict() if self._metadata else None,
        }
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.agent_type} state={self._status.state.value}>"


# 类型别名，便于导入
# AgentTask 类型定义已统一到 agents.priority 模块
# 请使用: from agents.priority import AgentTask
# 
# 注意: 此处保留 AgentTask 类型别名仅用于向后兼容
# 新代码请使用 agents.priority.AgentTask dataclass
try:
    from agents.priority import AgentTask
except ImportError:
    # 回退定义 (仅当无法导入时使用)
    AgentTask = Dict[str, Any]  # type: ignore
