"""
Agent优先级和任务定义

V2.0版本
创建日期: 2026-03-21
"""

from enum import IntEnum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


class TaskPriority(IntEnum):
    """任务优先级枚举"""

    CRITICAL = 0  # 紧急任务:用户主动触发的生成任务
    HIGH = 1  # 高优先:插件热重载、配置变更
    NORMAL = 2  # 正常:后台分析、统计计算
    LOW = 3  # 低优先:日志归档、缓存清理
    BACKGROUND = 4  # 后台:监控数据收集


@dataclass
class AgentTask:
    """Agent任务"""

    task_id: str  # 任务唯一标识
    agent_type: str  # Agent类型 (thinker/optimizer/validator/planner)
    priority: TaskPriority  # 优先级
    payload: Dict[str, Any]  # 任务载荷
    dependencies: List[str] = field(default_factory=list)  # 依赖任务ID列表
    created_at: Optional[datetime] = None  # 创建时间
    started_at: Optional[datetime] = None  # 开始时间
    completed_at: Optional[datetime] = None  # 完成时间
    retry_count: int = 0  # 重试次数
    max_retries: int = 3  # 最大重试次数
    timeout_seconds: int = 300  # 超时时间(秒)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    @property
    def age_seconds(self) -> float:
        """任务年龄(秒)"""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()

    @property
    def is_expired(self) -> bool:
        """是否超时"""
        if self.started_at is None:
            return self.age_seconds > self.timeout_seconds
        return (
            datetime.now(timezone.utc) - self.started_at
        ).total_seconds() > self.timeout_seconds

    @property
    def can_retry(self) -> bool:
        """是否可以重试"""
        return self.retry_count < self.max_retries
