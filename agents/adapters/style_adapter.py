"""
风格学习器适配器

V2.0版本
创建日期: 2026-03-21
"""

import logging
from typing import Any, Dict

from ..agent_adapter import AgentAdapter
from ..priority import AgentTask

logger = logging.getLogger(__name__)


class StyleLearnerAdapter(AgentAdapter):
    """
    风格学习器适配器

    包装 scripts.enhanced_style_learner_v2.EnhancedStyleLearnerV2
    """

    def __init__(self):
        super().__init__(
            agent_type="style_learner",
            module_path="scripts.enhanced_style_learner_v2",
            class_name="EnhancedStyleLearnerV2",
        )

    def execute(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行风格学习

        Args:
            task: 任务对象

        Returns:
            学习结果
        """
        if not self._initialized or not self._wrapped_instance:
            raise RuntimeError(f"Agent {self.agent_type} 未初始化")

        payload = task.payload

        try:
            # 调用V5模块的learn方法
            result = self._wrapped_instance.learn(
                payload.get("sample_texts"), **payload.get("options", {})
            )

            # 更新状态
            self._increment_completed()

            return {
                "task_id": task.task_id,
                "result": result,
                "metadata": {
                    "vocabulary": len(result.get("vocabulary", {})),
                    "sentence_patterns": len(result.get("sentence_patterns", [])),
                },
            }

        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            logger.error(f"风格学习失败: {e}", exc_info=True)
            raise
