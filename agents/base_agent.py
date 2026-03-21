"""
Agent基类定义

V2.0版本
创建日期: 2026-03-21

特性:
- 抽象基类定义Agent接口
- 状态管理
- 健康检查
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from .priority import AgentTask
from .agent_state import AgentState, AgentStatus


class BaseAgent(ABC):
    """
    Agent抽象基类

    所有Agent必须实现以下方法:
    - initialize(): 初始化Agent
    - execute(task): 执行任务
    - can_handle(task): 判断是否能处理任务
    - cleanup(): 清理资源
    """

    def __init__(self, agent_type: str):
        """
        初始化Agent

        Args:
            agent_type: Agent类型标识
        """
        self.agent_type = agent_type
        self._status = AgentStatus(agent_type=agent_type, state=AgentState.UNLOADED)
        self._initialized = False

    @abstractmethod
    def initialize(self) -> bool:
        """
        初始化Agent

        Returns:
            是否初始化成功
        """
        pass

    @abstractmethod
    def execute(self, task: AgentTask) -> Any:
        """
        执行任务

        Args:
            task: 任务对象

        Returns:
            执行结果
        """
        pass

    @abstractmethod
    def can_handle(self, task: AgentTask) -> bool:
        """
        判断是否能处理该任务

        Args:
            task: 任务对象

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

    @property
    def status(self) -> AgentStatus:
        """获取Agent状态"""
        return self._status

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

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
            "last_active": (
                self._status.last_active.isoformat()
                if self._status.last_active
                else None
            ),
            "error_message": self._status.error_message,
        }

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
