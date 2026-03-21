"""
Agent上下文管理器

V2.0版本
创建日期: 2026-03-21

特性:
- 任务上下文管理
- 对话历史记录
- 跨任务上下文传递
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Agent上下文"""

    task_id: str  # 任务ID
    session_id: str  # 会话ID
    conversation_history: List[Dict] = field(default_factory=list)  # 对话历史
    shared_memory: Dict[str, Any] = field(default_factory=dict)  # 共享记忆
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at

    def add_message(self, role: str, content: str, **metadata):
        """添加消息到对话历史"""
        self.conversation_history.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **metadata,
            }
        )
        self.updated_at = datetime.now(timezone.utc)

    def get_recent_messages(self, n: int = 5) -> List[Dict]:
        """获取最近n条消息"""
        return self.conversation_history[-n:]

    def set_shared(self, key: str, value: Any):
        """设置共享记忆"""
        self.shared_memory[key] = value
        self.updated_at = datetime.now(timezone.utc)

    def get_shared(self, key: str, default: Any = None) -> Any:
        """获取共享记忆"""
        return self.shared_memory.get(key, default)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "conversation_history": self.conversation_history,
            "shared_memory": self.shared_memory,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ContextManager:
    """
    上下文管理器

    管理Agent任务的生命周期上下文
    """

    def __init__(self, max_history: int = 10):
        """
        初始化上下文管理器

        Args:
            max_history: 最大历史记录数
        """
        self._contexts: Dict[str, AgentContext] = {}
        self._max_history = max_history

    def create_context(self, task_id: str, session_id: str) -> AgentContext:
        """
        创建新上下文

        Args:
            task_id: 任务ID
            session_id: 会话ID

        Returns:
            AgentContext对象
        """
        context = AgentContext(task_id=task_id, session_id=session_id)
        self._contexts[task_id] = context
        return context

    def get_context(self, task_id: str) -> Optional[AgentContext]:
        """
        获取上下文

        Args:
            task_id: 任务ID

        Returns:
            AgentContext对象，不存在返回None
        """
        return self._contexts.get(task_id)

    def update_context(self, task_id: str, updates: Dict[str, Any]):
        """
        更新上下文

        Args:
            task_id: 任务ID
            updates: 更新内容
        """
        context = self.get_context(task_id)
        if not context:
            return

        for key, value in updates.items():
            setattr(context, key, value)

        context.updated_at = datetime.now(timezone.utc)

    def transfer_context(self, from_task: str, to_task: str, keys: List[str] = None):
        """
        传递上下文

        Args:
            from_task: 源任务ID
            to_task: 目标任务ID
            keys: 要传递的键列表(默认传递全部共享记忆)
        """
        from_ctx = self.get_context(from_task)
        to_ctx = self.get_context(to_task)

        if not from_ctx or not to_ctx:
            return

        if keys is None:
            # 传递全部共享记忆
            to_ctx.shared_memory.update(from_ctx.shared_memory)
        else:
            # 只传递指定键
            for key in keys:
                if key in from_ctx.shared_memory:
                    to_ctx.shared_memory[key] = from_ctx.shared_memory[key]

        to_ctx.updated_at = datetime.now(timezone.utc)

    def cleanup_context(self, task_id: str):
        """
        清理上下文

        Args:
            task_id: 任务ID
        """
        if task_id in self._contexts:
            del self._contexts[task_id]

    def get_active_contexts(self) -> List[AgentContext]:
        """
        获取所有活跃上下文

        Returns:
            AgentContext列表
        """
        return list(self._contexts.values())

    def cleanup_old_contexts(self, max_age_seconds: int = 3600):
        """
        清理过期的上下文

        Args:
            max_age_seconds: 最大存活时间（秒）
        """
        now = datetime.now(timezone.utc)
        expired = []

        for task_id, ctx in self._contexts.items():
            age = (now - ctx.updated_at).total_seconds()
            if age > max_age_seconds:
                expired.append(task_id)

        for task_id in expired:
            self.cleanup_context(task_id)

        if expired:
            logger.info(f"清理过期上下文 {len(expired)} 个")
