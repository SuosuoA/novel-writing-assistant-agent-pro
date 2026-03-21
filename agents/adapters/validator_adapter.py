"""
加权验证器适配器

V2.0版本
创建日期: 2026-03-21
"""

import logging
from typing import Any, Dict

from ..agent_adapter import AgentAdapter
from ..priority import AgentTask
from core.models import ValidationScores

logger = logging.getLogger(__name__)


class WeightedValidatorAdapter(AgentAdapter):
    """
    加权验证器适配器

    包装 scripts.enhanced_weighted_validator.EnhancedWeightedValidator

    注意：此模块为核心保护模块，不可破坏性修改
    """

    def __init__(self):
        super().__init__(
            agent_type="weighted_validator",
            module_path="scripts.enhanced_weighted_validator",
            class_name="EnhancedWeightedValidator",
        )

    def execute(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行验证

        Args:
            task: 任务对象

        Returns:
            验证结果
        """
        if not self._initialized or not self._wrapped_instance:
            raise RuntimeError(f"Agent {self.agent_type} 未初始化")

        payload = task.payload

        try:
            # 调用V5模块的validate方法
            result = self._wrapped_instance.validate(
                payload.get("content"), **payload.get("options", {})
            )

            # 更新状态
            self._increment_completed()

            # 计算是否通过阈值
            total_score = result.get("total_score", 0)
            passed_threshold = total_score >= 0.8 and result.get(
                "has_chapter_end", False
            )

            return {
                "task_id": task.task_id,
                "result": result,
                "metadata": {
                    "total_score": total_score,
                    "passed_threshold": passed_threshold,
                    "has_chapter_end": result.get("has_chapter_end", False),
                },
            }

        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            logger.error(f"验证失败: {e}", exc_info=True)
            raise
