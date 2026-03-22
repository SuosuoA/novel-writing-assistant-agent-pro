"""
Agent执行约束配置

V2.1版本（P1-4修复）
创建日期: 2026-03-21
更新日期: 2026-03-23

特性：
- 超时控制
- 重试限制
- 降级策略
- 资源限制
"""

from dataclasses import dataclass, field
from typing import Callable, Any, Dict, Optional
import signal
import threading


@dataclass
class AgentConstraints:
    """Agent执行约束配置"""

    timeout_seconds: int = 30
    max_retries: int = 1

    # P1-4修复：新增资源限制
    max_memory_mb: int = 512  # 最大内存使用（MB）
    max_output_size: int = 100000  # 最大输出大小（字符数）

    # P1-4修复：新增超时行为配置
    timeout_grace_period: int = 5  # 超时后优雅关闭等待时间
    force_kill_on_timeout: bool = True  # 超时后是否强制终止

    def get_fallback_strategy(self) -> Callable[[], Any]:
        """获取降级策略"""
        raise NotImplementedError

    def validate_constraints(self) -> bool:
        """
        P1-4修复：验证约束配置的有效性

        Returns:
            是否是有效的约束配置
        """
        if self.timeout_seconds <= 0:
            return False
        if self.max_retries < 0:
            return False
        if self.max_memory_mb <= 0:
            return False
        if self.timeout_grace_period < 0:
            return False
        return True


class TimeoutContext:
    """
    P1-4修复：超时上下文管理器

    用于在同步代码中实现超时控制
    """

    def __init__(self, timeout_seconds: int, grace_period: int = 5):
        """
        初始化超时上下文

        Args:
            timeout_seconds: 超时秒数
            grace_period: 优雅关闭等待时间
        """
        self._timeout = timeout_seconds
        self._grace_period = grace_period
        self._timer: Optional[threading.Timer] = None
        self._timed_out = False
        self._exception: Optional[TimeoutError] = None

    def __enter__(self):
        """进入上下文，启动超时定时器"""
        self._timed_out = False
        self._exception = None

        # Windows不支持SIGALRM，使用线程定时器
        def timeout_handler():
            self._timed_out = True

        self._timer = threading.Timer(self._timeout, timeout_handler)
        self._timer.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，取消定时器"""
        if self._timer:
            self._timer.cancel()
            self._timer = None

        if self._timed_out:
            self._exception = TimeoutError(
                f"Operation timed out after {self._timeout} seconds"
            )
            raise self._exception

        return False

    def check_timeout(self) -> None:
        """
        检查是否超时，如果超时则抛出异常

        Raises:
            TimeoutError: 如果已超时
        """
        if self._timed_out:
            raise TimeoutError(
                f"Operation timed out after {self._timeout} seconds"
            )


class ThinkerConstraints(AgentConstraints):
    """ThinkerAgent约束"""

    timeout_seconds: int = 30
    max_retries: int = 1
    max_memory_mb: int = 512
    max_output_size: int = 50000  # 推理输出不需要太大

    def get_fallback_strategy(self) -> Callable[[], Any]:
        """降级策略: 跳过CoT，使用直接推理"""
        return lambda: {"reasoning": "直接推理(降级模式)", "result": None}


class OptimizerConstraints(AgentConstraints):
    """OptimizerAgent约束"""

    timeout_seconds: int = 20
    max_retries: int = 1
    max_memory_mb: int = 256
    max_output_size: int = 100000

    def get_fallback_strategy(self) -> Callable[[], Any]:
        """降级策略: 返回原始生成结果"""
        return lambda: {"optimized": False, "reason": "优化超时，返回原始结果"}


class ValidatorConstraints(AgentConstraints):
    """ValidatorAgent约束"""

    timeout_seconds: int = 15
    max_retries: int = 0
    max_memory_mb: int = 128
    max_output_size: int = 1000  # 评分输出很小

    def get_fallback_strategy(self) -> Callable[[], Any]:
        """降级策略: 返回默认评分0.5"""
        from core.models import ValidationScores

        return lambda: ValidationScores(
            word_count_score=0.5,
            outline_score=0.5,
            style_score=0.5,
            character_score=0.5,
            worldview_score=0.5,
            naturalness_score=0.5,
        )


class PlannerConstraints(AgentConstraints):
    """PlannerAgent约束"""

    timeout_seconds: int = 10
    max_retries: int = 0
    max_memory_mb: int = 64
    max_output_size: int = 5000

    def get_fallback_strategy(self) -> Callable[[], Any]:
        """降级策略: 使用上一次计划"""
        return lambda: {"plan": "使用上一次计划(降级模式)", "tasks": []}
