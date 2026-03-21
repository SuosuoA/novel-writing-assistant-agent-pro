"""
Agent执行约束配置

V2.0版本
创建日期: 2026-03-21
"""

from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class AgentConstraints:
    """Agent执行约束配置"""

    timeout_seconds: int = 30
    max_retries: int = 1

    def get_fallback_strategy(self) -> Callable[[], Any]:
        """获取降级策略"""
        raise NotImplementedError


class ThinkerConstraints(AgentConstraints):
    """ThinkerAgent约束"""

    timeout_seconds: int = 30
    max_retries: int = 1

    def get_fallback_strategy(self) -> Callable[[], Any]:
        """降级策略: 跳过CoT，使用直接推理"""
        return lambda: {"reasoning": "直接推理(降级模式)", "result": None}


class OptimizerConstraints(AgentConstraints):
    """OptimizerAgent约束"""

    timeout_seconds: int = 20
    max_retries: int = 1

    def get_fallback_strategy(self) -> Callable[[], Any]:
        """降级策略: 返回原始生成结果"""
        return lambda: {"optimized": False, "reason": "优化超时，返回原始结果"}


class ValidatorConstraints(AgentConstraints):
    """ValidatorAgent约束"""

    timeout_seconds: int = 15
    max_retries: int = 0

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

    def get_fallback_strategy(self) -> Callable[[], Any]:
        """降级策略: 使用上一次计划"""
        return lambda: {"plan": "使用上一次计划(降级模式)", "tasks": []}
