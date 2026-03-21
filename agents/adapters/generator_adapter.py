"""
迭代生成器适配器

V2.0版本
创建日期: 2026-03-21
"""

import logging
from typing import Any, Dict

from ..agent_adapter import AgentAdapter
from ..priority import AgentTask

logger = logging.getLogger(__name__)


class IterativeGeneratorAdapter(AgentAdapter):
    """
    迭代生成器适配器

    包装 scripts.iterative_generator_v2.IterativeGeneratorV2

    注意：此模块为核心保护模块，不可破坏性修改
    """

    def __init__(self):
        super().__init__(
            agent_type="iterative_generator",
            module_path="scripts.iterative_generator_v2",
            class_name="IterativeGeneratorV2",
        )

    def execute(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行迭代生成

        Args:
            task: 任务对象

        Returns:
            生成结果
        """
        if not self._initialized or not self._wrapped_instance:
            raise RuntimeError(f"Agent {self.agent_type} 未初始化")

        payload = task.payload

        try:
            # 调用V5模块的generate方法
            result = self._wrapped_instance.generate(
                prompt=payload.get("prompt"),
                max_iterations=payload.get("max_iterations", 5),
                **payload.get("options", {}),
            )

            # 更新状态
            self._increment_completed()

            return {
                "task_id": task.task_id,
                "result": result,
                "metadata": {
                    "iterations": result.get("iterations", 0),
                    "final_score": result.get("final_score", 0),
                    "content_length": len(result.get("content", "")),
                    "has_chapter_end": result.get("has_chapter_end", False),
                },
            }

        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            logger.error(f"迭代生成失败: {e}", exc_info=True)
            raise
