"""
Agent状态管理

V2.0版本
创建日期: 2026-03-21
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any


class AgentState(Enum):
    """Agent状态枚举"""

    UNLOADED = "unloaded"  # 未加载
    LOADED = "loaded"  # 已加载(初始化中)
    ACTIVE = "active"  # 活跃(可接受任务)
    ERROR = "error"  # 错误(无法使用)
    SHUTTING_DOWN = "shutting_down"  # 正在关闭


@dataclass
class AgentStatus:
    """Agent状态信息"""

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

    def update_last_active(self):
        """更新最后活跃时间"""
        self.last_active = datetime.now(timezone.utc)

    def increment_completed(self):
        """任务完成计数+1"""
        self.tasks_completed += 1
        self.update_last_active()

    def increment_failed(self):
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
            "initialized_at": (
                self.initialized_at.isoformat() if self.initialized_at else None
            ),
        }
