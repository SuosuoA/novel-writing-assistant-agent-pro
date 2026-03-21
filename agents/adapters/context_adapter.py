"""
上下文构建器适配器

V2.0版本
创建日期: 2026-03-21
"""

import logging
from typing import Any, Dict

from ..agent_adapter import AgentAdapter
from ..priority import AgentTask

logger = logging.getLogger(__name__)


class ContextBuilderAdapter(AgentAdapter):
    """
    上下文构建器适配器

    包装 scripts.context_builder.SmartContextBuilder
    """

    def __init__(self):
        super().__init__(
            agent_type="context_builder",
            module_path="scripts.context_builder",
            class_name="SmartContextBuilder",
        )

    def execute(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行上下文构建

        Args:
            task: 任务对象

        Returns:
            构建结果
        """
        if not self._initialized or not self._wrapped_instance:
            raise RuntimeError(f"Agent {self.agent_type} 未初始化")

        payload = task.payload

        try:
            # 调用V5模块的build方法
            result = self._wrapped_instance.build(
                worldview=payload.get("worldview"),
                characters=payload.get("characters"),
                outline=payload.get("outline"),
                style_profile=payload.get("style_profile"),
                **payload.get("options", {}),
            )

            # 更新状态
            self._increment_completed()

            return {
                "task_id": task.task_id,
                "result": result,
                "metadata": {
                    "prompt_length": len(result.get("prompt", "")),
                    "sections_count": len(result.get("sections", [])),
                },
            }

        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            logger.error(f"上下文构建失败: {e}", exc_info=True)
            raise
